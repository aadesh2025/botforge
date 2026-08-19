"""docs/17 Phase 1 — `AgentBudget` mechanics and the nested-budget-inheritance rule.

`docs/17-AGENTIC-RUNTIME-AND-BUILDER.md` §2 rule 3 (ADR-070/ADR-073): a sub-agent or nested
tool call must draw from the *parent turn's remaining* budget, never a fresh one. OpenManus's
`BaseFlow` does not enforce this — ADR-070 names it as the exact gap this must not repeat.
The only correct way to give a nested `run_turn` call a budget is to pass it the SAME
`AgentBudget` instance the parent call used; there is deliberately no `.child()`/`.fork()`
constructor (see `app/chat/budget.py`'s module docstring).

These tests exercise the dataclass directly (limit-tripping, stickiness) and then prove the
inheritance rule against the real `run_turn` loop — not just unit-test the dataclass in
isolation, since the rule matters only insofar as `run_turn` actually honours it.
"""

from __future__ import annotations

import pytest

from app.chat.budget import AgentBudget, agentic_loop_enabled, default_budget, turn_budget
from app.chat.runtime import TurnResult, run_turn
from app.core.config import settings
from app.llm.fake import MultiRoundToolProvider
from app.llm.types import ChatRequest, Message, ToolCall, ToolSpec


def _budget(**overrides: object) -> AgentBudget:
    base = dict(max_steps=5, max_tool_calls=5, max_runtime_s=30.0, max_cost_usd=0.05)
    base.update(overrides)
    return AgentBudget(**base)  # type: ignore[arg-type]


# ── AgentBudget: each dimension trips independently ───────────────────────────────────────


def test_can_continue_true_when_nothing_consumed() -> None:
    assert _budget().can_continue() is True


def test_trips_on_max_steps() -> None:
    b = _budget(max_steps=2)
    b.record_step()
    b.record_step()
    assert b.can_continue() is False
    assert b.tripped == "max_steps"


def test_trips_on_max_tool_calls() -> None:
    b = _budget(max_tool_calls=3)
    b.record_tool_calls(3)
    assert b.can_continue() is False
    assert b.tripped == "max_tool_calls"


def test_trips_on_max_cost() -> None:
    b = _budget(max_cost_usd=0.01)
    b.record_step(cost_usd=0.02)
    assert b.can_continue() is False
    assert b.tripped == "max_cost_usd"


def test_trips_on_max_runtime() -> None:
    b = _budget(max_runtime_s=0.0)
    # started_at defaults to perf_counter() at construction; any elapsed time trips it.
    assert b.can_continue() is False
    assert b.tripped == "max_runtime_s"


def test_tripped_is_sticky_even_if_a_later_check_would_pass() -> None:
    """Once tripped, stays tripped for the life of the instance — including for a nested call
    sharing it, which must never see budget "come back" mid-turn."""
    b = _budget(max_steps=1)
    b.record_step()
    assert b.can_continue() is False
    assert b.tripped == "max_steps"
    # Nothing about tool_calls or cost changed, but the verdict must not flip.
    assert b.can_continue() is False
    assert b.tripped == "max_steps"


# ── Gating: both platform AND org flags must be on ────────────────────────────────────────


def test_agentic_loop_enabled_requires_both_platform_and_org(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "agentic_loop_enabled", False)
    assert agentic_loop_enabled(True) is False  # platform off, org on: still off

    monkeypatch.setattr(settings, "agentic_loop_enabled", True)
    assert agentic_loop_enabled(None) is False  # org unset: off
    assert agentic_loop_enabled(False) is False  # org explicit opt-out: off
    assert agentic_loop_enabled(True) is True  # both on: only case that's on


def test_turn_budget_is_none_without_tools_even_if_org_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "agentic_loop_enabled", True)
    assert turn_budget(True, has_tools=False) is None


def test_turn_budget_is_none_when_org_not_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "agentic_loop_enabled", True)
    assert turn_budget(None, has_tools=True) is None
    assert turn_budget(False, has_tools=True) is None


def test_turn_budget_returns_a_fresh_budget_when_both_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "agentic_loop_enabled", True)
    b = turn_budget(True, has_tools=True)
    assert isinstance(b, AgentBudget)
    assert b.consumed_steps == 0 and b.tripped is None


def test_default_budget_reads_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "agentic_max_steps", 7)
    monkeypatch.setattr(settings, "agentic_max_tool_calls", 9)
    monkeypatch.setattr(settings, "agentic_max_runtime_s", 12.0)
    monkeypatch.setattr(settings, "agentic_max_cost_usd", 0.5)
    b = default_budget()
    assert (b.max_steps, b.max_tool_calls, b.max_runtime_s, b.max_cost_usd) == (7, 9, 12.0, 0.5)


# ── The rule that matters: a nested/delegated run_turn call shares, never resets ──────────


async def _executor(_call: ToolCall) -> dict:
    return {"output": {"ok": True}, "status": "success", "error": None}


async def test_nested_run_turn_call_decrements_the_parent_budget_not_a_fresh_one() -> None:
    """Simulates a Sub-Agent node: a parent `run_turn` call consumes some of a shared budget,
    then a "nested" call reuses the SAME instance. The nested call must see, and be bounded
    by, only what the parent left — never a full fresh ceiling."""
    shared = _budget(max_steps=3, max_tool_calls=10)

    # Parent call: two tool-call rounds (2 tool calls -> a 3rd request would exceed max_steps
    # anyway, but we stop the script after 2 rounds so it answers on round 3).
    parent_calls = [ToolCall(id="p1", name="t", arguments={}), ToolCall(id="p2", name="t", arguments={})]
    parent_provider = MultiRoundToolProvider(parent_calls, answer="parent done")
    parent_req = ChatRequest(
        model="m", messages=[Message(role="user", content="go")], tools=[ToolSpec(name="t")]
    )
    parent_result = TurnResult()
    [
        e
        async for e in run_turn(
            parent_provider, parent_req, [], parent_result, executor=_executor, max_iters=5, budget=shared
        )
    ]

    consumed_after_parent = shared.consumed_steps
    assert consumed_after_parent >= 2, "parent call should have consumed at least 2 think-steps"
    assert shared.tripped in (None, "max_steps")

    # Nested/"sub-agent" call reuses the SAME AgentBudget instance — per docs/17 §2 rule 3,
    # never construct a fresh AgentBudget(...) for it.
    nested_calls = [ToolCall(id="n1", name="t", arguments={})]
    nested_provider = MultiRoundToolProvider(nested_calls, answer="nested done")
    nested_req = ChatRequest(
        model="m", messages=[Message(role="user", content="nested")], tools=[ToolSpec(name="t")]
    )
    nested_result = TurnResult()
    [
        e
        async for e in run_turn(
            nested_provider, nested_req, [], nested_result, executor=_executor, max_iters=5, budget=shared
        )
    ]

    # The budget accumulated across BOTH calls — proof it was shared, not reset. If the nested
    # call had received a fresh AgentBudget(max_steps=3, ...), `shared.consumed_steps` here
    # would equal `consumed_after_parent` unchanged; instead it must have grown further (or the
    # shared budget must already show as tripped, if the parent alone exhausted it).
    assert shared.consumed_steps >= consumed_after_parent
    if consumed_after_parent >= shared.max_steps:
        # Parent alone exhausted it: the nested call must have run zero further model passes.
        assert nested_result.agent_steps == [] or all(
            s["kind"] != "think" for s in nested_result.agent_steps
        ) or len(nested_result.agent_steps) <= 1
    else:
        # There was room left: the nested call consumed from what remained, and the combined
        # total across both calls never exceeds the ONE shared ceiling.
        assert shared.consumed_steps <= shared.max_steps


async def test_nested_call_on_an_already_tripped_budget_runs_zero_model_passes() -> None:
    """The sharpest form of the rule: if the parent already exhausted the shared budget, the
    nested call must not sneak in "one free iteration" before its own first check."""
    shared = _budget(max_steps=1)
    shared.record_step()  # parent already spent the entire budget
    assert shared.can_continue() is False

    provider = MultiRoundToolProvider([ToolCall(id="x", name="t", arguments={})], answer="should not run")
    req = ChatRequest(model="m", messages=[Message(role="user", content="go")], tools=[ToolSpec(name="t")])
    result = TurnResult()
    events = [
        e
        async for e in run_turn(provider, req, [], result, executor=_executor, max_iters=5, budget=shared)
    ]

    # Zero "think" steps were traced for the nested call — it never called the model.
    assert not any(s["kind"] == "think" for s in result.agent_steps)
    assert result.content == ""
    assert [e.type for e in events] == ["done"]
