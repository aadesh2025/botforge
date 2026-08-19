"""The agentic loop's budget (docs/17 §5, ADR-070/ADR-073).

`AgentBudget` is a single mutable object that `run_turn` decrements as it goes. There is
deliberately no `.child()` / `.fork()` constructor that hands out a fresh ceiling: docs/17 §2
rule 3 requires nested/sub-agent calls to draw from the *parent turn's remaining* allowance,
never a fresh one — OpenManus does not enforce this (ADR-070's finding: `BaseFlow` never
propagates `max_steps` into a spawned sub-agent) and that gap is exactly what this must not
repeat. The only correct way to give a nested call a budget is to pass it this same instance.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from app.core.config import settings


def agentic_loop_enabled(org_enabled: bool | None) -> bool:
    """Platform AND per-org gate — both must be explicitly on.

    Unlike `guard_injection_enabled`'s "on unless the org opts out" polarity,
    `settings.agentic_loop_enabled` defaults off and an org's own flag must be explicitly
    `True` to run the agentic loop; `None` or `False` both mean "off" for that org. A platform
    flip alone never turns any org on, and an org can never force it on when the platform
    switch is off — this is new attack surface and new cost exposure (docs/17 §2), so nothing
    is live until both levels agree. See ADR-073 for the rollout decision this encodes.
    """
    return bool(settings.agentic_loop_enabled and org_enabled is True)


@dataclass
class AgentBudget:
    max_steps: int
    max_tool_calls: int
    max_runtime_s: float
    max_cost_usd: float
    consumed_steps: int = 0
    consumed_tool_calls: int = 0
    consumed_cost_usd: float = 0.0
    started_at: float = field(default_factory=time.perf_counter)
    # Which limit tripped, once one does. Sticky — once tripped, stays tripped for the rest
    # of this budget's lifetime (including across nested calls sharing the same instance).
    tripped: str | None = None

    def elapsed_s(self) -> float:
        return time.perf_counter() - self.started_at

    def can_continue(self) -> bool:
        """Whether another step may run. Evaluates and (if applicable) sets `tripped`."""
        if self.tripped is not None:
            return False
        if self.consumed_steps >= self.max_steps:
            self.tripped = "max_steps"
        elif self.consumed_tool_calls >= self.max_tool_calls:
            self.tripped = "max_tool_calls"
        elif self.elapsed_s() >= self.max_runtime_s:
            self.tripped = "max_runtime_s"
        elif self.consumed_cost_usd >= self.max_cost_usd:
            self.tripped = "max_cost_usd"
        return self.tripped is None

    def record_step(self, *, cost_usd: float = 0.0) -> None:
        self.consumed_steps += 1
        self.consumed_cost_usd += cost_usd

    def record_tool_calls(self, count: int) -> None:
        self.consumed_tool_calls += count


def default_budget() -> AgentBudget:
    """A fresh top-level budget from the platform defaults (docs/17 §5)."""
    return AgentBudget(
        max_steps=settings.agentic_max_steps,
        max_tool_calls=settings.agentic_max_tool_calls,
        max_runtime_s=settings.agentic_max_runtime_s,
        max_cost_usd=settings.agentic_max_cost_usd,
    )


def turn_budget(org_enabled: bool | None, *, has_tools: bool) -> AgentBudget | None:
    """A fresh top-level budget for this turn, or `None` when there's nothing to bound.

    `None` when the agentic runtime is off for this org (`agentic_loop_enabled`), or when the
    turn has no tools to loop over anyway — a budget with nothing to spend on is just overhead
    (and `run_turn` treats `budget=None` as "today's behavior, untraced", which is exactly what
    a no-tools turn should get regardless of the org's setting).
    """
    if not has_tools or not agentic_loop_enabled(org_enabled):
        return None
    return default_budget()
