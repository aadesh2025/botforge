"""The workflow graph execution engine (docs/17 Phase 2 §3.1, ADR-074).

A workflow version's `graph` is `{"nodes": [{"id","type","config"}], "edges": [{"source",
"target","condition"}]}`. `run_workflow()` walks it node by node — synchronously, in one call,
the same shape `app.chat.runtime.run_turn` uses for its own step loop — and reuses
`app.chat.budget.AgentBudget` rather than inventing a second bounding mechanism: a workflow
run is bounded exactly the way an agentic chat turn is (steps/tool-calls/runtime/cost), and a
Sub-Agent node (not built this slice) sharing the SAME budget instance as its parent workflow
run gets the inheritance rule from docs/17 §2 rule 3 for free.

**Node types shipped this slice:** start, end, message, condition, set_variable, approval,
tool. Deliberately NOT shipped: switch (condition covers the two-way case; N-way needs its own
edge-selection design), loop, transform, delay, agent, sub-agent, get_variable (redundant with
template substitution — a Message/Condition node already reads any variable by name). See
docs/PROGRESS.md's Phase 2 entry for the reasoning; adding one is a registry entry in
`NODE_HANDLERS` plus an edge-selection case in `_next_node`, not a rearchitecture.

**Security, not incidental:**
- `evaluate_condition()` is a narrow hand-rolled parser (`var OP literal`, five operators, no
  boolean chaining) — never `eval()`. docs/17 §11 rules out arbitrary code execution outright;
  a condition node is exactly the place a careless implementation would reach for `eval` and
  exactly the place that decision would matter.
- `render_workflow_template()` reuses `app.chat.variables.escape_value()` (Phase F) for the
  same reason Phase F needed it: a workflow variable's value can originate from a visitor
  (e.g. a Set Variable node fed by a form field), so it is escaped and length-capped before
  ever appearing in a Message node's rendered text, single-pass, unknown vars render empty.
- A `tool` node's result is untrusted input, no exception for being "one of ours" — it goes
  through `neutralize_injections()` before it can be stored into a variable or referenced by a
  later Message node, the identical rule docs/17 §6 already enforces in `run_turn`.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from app.chat.budget import AgentBudget
from app.chat.guardrails import neutralize_injections
from app.chat.variables import escape_value

# (tool_name, arguments) -> {"output": dict, "status": str, "error": str | None} — identical
# shape to app.chat.runtime.ToolExecutor, deliberately, so the same tool dispatch used for
# chat can be reused here without an adapter.
WorkflowToolExecutor = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]

NODE_TYPES = frozenset({"start", "end", "message", "condition", "set_variable", "approval", "tool"})
_TERMINAL_TYPES = frozenset({"end"})


class WorkflowError(Exception):
    """A malformed graph or an unrecoverable execution error."""


@dataclass
class NodeResult:
    status: str  # completed | failed | awaiting_approval
    output: dict[str, Any] | None = None
    error: str | None = None
    cost_usd: float = 0.0
    # The edge-selection label a condition/approval node produced (e.g. "true"/"false",
    # "approved"/"rejected"). None for nodes with a single unconditional outgoing edge.
    branch: str | None = None


@dataclass
class WorkflowRunResult:
    status: str  # completed | paused_approval | failed | budget_exceeded
    variables: dict[str, Any]
    steps: list[dict[str, Any]] = field(default_factory=list)
    current_node_id: str | None = None
    error: str | None = None


# ── Graph validation (docs/17 §3: validated at save time, not accepted as opaque JSON) ────


def validate_graph(graph: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []
    if not isinstance(nodes, list) or not nodes:
        return ["graph.nodes must be a non-empty list"]
    ids = [n.get("id") for n in nodes]
    if len(ids) != len(set(ids)):
        errors.append("duplicate node id")
    node_ids = set(ids)
    for n in nodes:
        if n.get("type") not in NODE_TYPES:
            errors.append(f"unknown node type {n.get('type')!r} (node {n.get('id')!r})")
    starts = [n for n in nodes if n.get("type") == "start"]
    if len(starts) != 1:
        errors.append(f"graph must have exactly one start node, found {len(starts)}")
    ends = [n for n in nodes if n.get("type") == "end"]
    if not ends:
        errors.append("graph must have at least one end node")
    for e in edges:
        if e.get("source") not in node_ids:
            errors.append(f"edge source {e.get('source')!r} is not a node in this graph")
        if e.get("target") not in node_ids:
            errors.append(f"edge target {e.get('target')!r} is not a node in this graph")
    return errors


# ── Condition evaluation: a narrow parser, never eval() (docs/17 §11) ─────────────────────

_COND_RE = re.compile(
    r"^\s*([a-zA-Z_][a-zA-Z0-9_.]*)\s*(==|!=|>=|<=|>|<|contains)\s*(.+?)\s*$"
)


def _coerce_literal(raw: str) -> Any:
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ("'", '"'):
        return raw[1:-1]
    if raw in ("true", "True"):
        return True
    if raw in ("false", "False"):
        return False
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        return raw


def evaluate_condition(expression: str, variables: dict[str, Any]) -> bool:
    """`var.path OP literal` only — five operators, no boolean chaining, no eval().

    Matches the shape docs/17's own examples use (`intent == 'booking'`, `lead.score > 50`).
    An expression that doesn't parse is a `WorkflowError`, not a silently-false condition —
    a workflow author needs to see that their expression is malformed, not watch every branch
    silently take the same path.
    """
    match = _COND_RE.match(expression or "")
    if not match:
        raise WorkflowError(f"unsupported condition expression: {expression!r}")
    var_path, op, rhs_raw = match.groups()
    left = variables.get(var_path)
    right = _coerce_literal(rhs_raw)
    if op == "==":
        return bool(left == right)
    if op == "!=":
        return bool(left != right)
    if op == "contains":
        return right in (left or "")
    if left is None:
        return False
    try:
        if op == ">":
            return bool(left > right)
        if op == "<":
            return bool(left < right)
        if op == ">=":
            return bool(left >= right)
        if op == "<=":
            return bool(left <= right)
    except TypeError:
        return False
    return False


# ── Template substitution: reuses Phase F's escaping discipline ───────────────────────────

_VAR_PATTERN = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_.]*)\s*\}\}")


def render_workflow_template(template: str | None, variables: dict[str, Any]) -> str:
    """Single-pass `{{var.path}}` substitution. Unknown/unset variables render empty, never
    the literal placeholder — same rule `app.chat.variables.render()` uses, for the same
    reason: a missing value should read as a gap in the sentence, not as visible machinery.
    """
    if not template:
        return template or ""
    if "{{" not in template:
        return template

    def _replace(match: re.Match[str]) -> str:
        value = variables.get(match.group(1))
        if value is None:
            return ""
        return escape_value(str(value))

    return _VAR_PATTERN.sub(_replace, template)


# ── Node handlers ──────────────────────────────────────────────────────────────────────────


async def _run_start(node: dict[str, Any], variables: dict[str, Any], _executor: Any) -> NodeResult:
    return NodeResult(status="completed", output={})


async def _run_end(node: dict[str, Any], variables: dict[str, Any], _executor: Any) -> NodeResult:
    return NodeResult(status="completed", output={})


async def _run_message(node: dict[str, Any], variables: dict[str, Any], _executor: Any) -> NodeResult:
    content = render_workflow_template((node.get("config") or {}).get("content"), variables)
    return NodeResult(status="completed", output={"content": content})


async def _run_set_variable(
    node: dict[str, Any], variables: dict[str, Any], _executor: Any
) -> NodeResult:
    config = node.get("config") or {}
    key = config.get("key")
    if not key or not isinstance(key, str):
        return NodeResult(status="failed", error="set_variable requires config.key")
    rendered = render_workflow_template(str(config.get("value", "")), variables)
    variables[key] = rendered
    return NodeResult(status="completed", output={key: rendered})


async def _run_condition(
    node: dict[str, Any], variables: dict[str, Any], _executor: Any
) -> NodeResult:
    expression = (node.get("config") or {}).get("expression", "")
    try:
        outcome = evaluate_condition(expression, variables)
    except WorkflowError as exc:
        return NodeResult(status="failed", error=str(exc))
    return NodeResult(status="completed", output={"result": outcome}, branch="true" if outcome else "false")


async def _run_approval(
    node: dict[str, Any],
    variables: dict[str, Any],
    _executor: Any,
    *,
    resume_input: dict[str, Any] | None = None,
) -> NodeResult:
    if resume_input is None:
        # First visit: pause. The caller persists `current_node_id` (this node) and resumes
        # later by calling run_workflow again with resume_input={"decision": "approved"|...}.
        message = render_workflow_template((node.get("config") or {}).get("message"), variables)
        return NodeResult(status="awaiting_approval", output={"message": message})
    decision = resume_input.get("decision") or "rejected"
    if decision not in ("approved", "rejected"):
        decision = "rejected"
    return NodeResult(status="completed", output={"decision": decision}, branch=decision)


async def _run_tool(
    node: dict[str, Any],
    variables: dict[str, Any],
    executor: WorkflowToolExecutor | None,
) -> NodeResult:
    config = node.get("config") or {}
    tool_name = config.get("tool_name")
    if not tool_name:
        return NodeResult(status="failed", error="tool node requires config.tool_name")
    if executor is None:
        return NodeResult(status="failed", error="no tool executor configured for this run")
    raw_args = config.get("arguments") or {}
    rendered_args = {
        k: (render_workflow_template(v, variables) if isinstance(v, str) else v)
        for k, v in raw_args.items()
    }
    out = await executor(tool_name, rendered_args)
    # Untrusted, no exception for tool source (docs/17 §6) — identical treatment to
    # `run_turn`'s `neutralize_injections(json.dumps(out.get("output") or {}))` call.
    sanitized_text = neutralize_injections(json.dumps(out.get("output") or {}))
    result_variable = config.get("result_variable")
    if result_variable:
        variables[result_variable] = sanitized_text
    return NodeResult(
        status="failed" if out.get("status") == "error" else "completed",
        output={"sanitized_text": sanitized_text},
        error=out.get("error"),
    )


_HANDLERS: dict[str, Callable[..., Awaitable[NodeResult]]] = {
    "start": _run_start,
    "end": _run_end,
    "message": _run_message,
    "set_variable": _run_set_variable,
    "condition": _run_condition,
    "approval": _run_approval,
    "tool": _run_tool,
}


def _next_node(
    node_id: str, edges: list[dict[str, Any]], branch: str | None
) -> str | None:
    candidates = [e for e in edges if e.get("source") == node_id]
    if not candidates:
        return None
    if branch is not None:
        for e in candidates:
            if e.get("condition") == branch:
                return e.get("target")
        return None  # no matching branch edge — the graph author didn't wire this outcome
    return candidates[0].get("target")


# ── The loop ─────────────────────────────────────────────────────────────────────────────


async def run_workflow(
    graph: dict[str, Any],
    *,
    variables: dict[str, Any],
    budget: AgentBudget,
    tool_executor: WorkflowToolExecutor | None = None,
    start_node_id: str | None = None,
    resume_input: dict[str, Any] | None = None,
) -> WorkflowRunResult:
    """Execute `graph` starting at `start_node_id` (or the graph's `start` node), until it
    reaches an `end` node, pauses on an `approval` node, fails, or exhausts `budget`.

    `budget` is the SAME `AgentBudget` instance a caller may already be spending from (docs/17
    §2 rule 3) — this function never constructs its own. Passing a fresh one is the caller's
    decision to make, not this function's.

    Resuming a paused run: call again with `start_node_id` set to the `current_node_id` the
    previous `WorkflowRunResult` returned, and `resume_input={"decision": "approved"|
    "rejected"}`. Everything upstream of that node is not re-executed — this function has no
    memory of it, which is why the caller (the service layer, not this module) is responsible
    for persisting `variables` and `budget` between calls.
    """
    errors = validate_graph(graph)
    if errors:
        return WorkflowRunResult(status="failed", variables=variables, error="; ".join(errors))

    nodes_by_id = {n["id"]: n for n in graph["nodes"]}
    edges = graph.get("edges") or []
    current = start_node_id or next(n["id"] for n in graph["nodes"] if n["type"] == "start")
    steps: list[dict[str, Any]] = []
    first_iteration = True

    while True:
        node = nodes_by_id.get(current)
        if node is None:
            return WorkflowRunResult(
                status="failed", variables=variables, steps=steps, current_node_id=current,
                error=f"unknown node {current!r}",
            )
        if not budget.can_continue():
            return WorkflowRunResult(
                status="budget_exceeded", variables=variables, steps=steps, current_node_id=current,
            )

        handler = _HANDLERS[node["type"]]
        t0 = time.perf_counter()
        if node["type"] == "approval":
            result = await handler(
                node, variables, tool_executor,
                resume_input=resume_input if first_iteration else None,
            )
        elif node["type"] == "tool":
            budget.record_tool_calls(1)
            result = await handler(node, variables, tool_executor)
        else:
            result = await handler(node, variables, tool_executor)
        first_iteration = False
        latency_ms = int((time.perf_counter() - t0) * 1000)
        budget.record_step(cost_usd=result.cost_usd)

        steps.append({
            "node_id": current, "node_type": node["type"],
            "status": "awaiting_approval" if result.status == "awaiting_approval" else result.status,
            "input": None, "output": result.output, "latency_ms": latency_ms,
            "cost_usd": result.cost_usd, "error": result.error,
        })

        if result.status == "failed":
            return WorkflowRunResult(
                status="failed", variables=variables, steps=steps, current_node_id=current,
                error=result.error,
            )
        if result.status == "awaiting_approval":
            return WorkflowRunResult(
                status="paused_approval", variables=variables, steps=steps, current_node_id=current,
            )
        if node["type"] in _TERMINAL_TYPES:
            return WorkflowRunResult(status="completed", variables=variables, steps=steps, current_node_id=None)

        nxt = _next_node(current, edges, result.branch)
        if nxt is None:
            return WorkflowRunResult(
                status="failed", variables=variables, steps=steps, current_node_id=current,
                error=f"node {current!r} has no outgoing edge for branch {result.branch!r}",
            )
        current = nxt
