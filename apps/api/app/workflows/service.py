"""Workflow CRUD, versioning, and execution (docs/17 Phase 2).

Execution is synchronous-in-request for this slice (no Celery wiring yet — see
docs/PROGRESS.md's Phase 2 entry): `run_workflow_now`/`resume_workflow_run` call
`app.workflows.graph.run_workflow` directly and persist the result. The `WorkflowRun` row is
still the resumability boundary — `variables`/`budget`/`current_node_id` are read back from
the DB on resume, not kept in process memory, so a future Celery task can drive the exact same
functions without a rewrite; only the "who calls it and when" changes.

Every run gets a budget from `app.chat.budget.default_budget()` unconditionally — unlike
Phase 1's dual platform+org flag (which had to gate a change to every existing agent's default
chat behavior), a workflow is a brand-new object type nobody has until an org with
`WORKFLOWS_WRITE` creates one, so RBAC is already the opt-in gate; a second rollout flag would
be redundant. See ADR-074.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat import variables as chat_variables
from app.chat.assembly import compose_system_prompt
from app.chat.budget import AgentBudget, default_budget
from app.chat.runtime import TurnResult, run_turn
from app.core import rbac
from app.core.errors import AppError
from app.core.logging import get_logger
from app.llm.registry import get_chat_provider, get_chat_provider_chain
from app.llm.types import ChatRequest, Message, ToolCall
from app.models import Agent, AgentVersion, Workflow, WorkflowRun, WorkflowStep, WorkflowVersion
from app.modules.orgs.deps import OrgContext
from app.tools.base import ToolContext
from app.tools.service import execute_tool_call, resolve_agent_tools
from app.workflows import schemas
from app.workflows.graph import (
    WorkflowAgentExecutor,
    WorkflowRunResult,
    WorkflowSubExecutor,
    run_workflow,
    validate_graph,
)

log = get_logger("workflows")


# ── Internals ────────────────────────────────────────────────────────────────────────────


async def _get_workflow(session: AsyncSession, ctx: OrgContext, workflow_id: uuid.UUID) -> Workflow:
    workflow = await session.get(Workflow, workflow_id)
    if workflow is None or workflow.organization_id != ctx.org.id or workflow.deleted_at is not None:
        raise AppError("workflows.not_found", "Workflow not found.", 404)
    return workflow


async def _get_version(
    session: AsyncSession, workflow_id: uuid.UUID, version: int
) -> WorkflowVersion:
    stmt = select(WorkflowVersion).where(
        WorkflowVersion.workflow_id == workflow_id, WorkflowVersion.version == version
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise AppError("workflows.version_not_found", "Workflow version not found.", 404)
    return row


async def _get_run(session: AsyncSession, ctx: OrgContext, run_id: uuid.UUID) -> WorkflowRun:
    run = await session.get(WorkflowRun, run_id)
    if run is None or run.organization_id != ctx.org.id:
        raise AppError("workflows.run_not_found", "Workflow run not found.", 404)
    return run


def _workflow_out(w: Workflow) -> schemas.WorkflowOut:
    return schemas.WorkflowOut(
        id=w.id, organization_id=w.organization_id, agent_id=w.agent_id, name=w.name,
        description=w.description, current_version_id=w.current_version_id,
        created_at=w.created_at, updated_at=w.updated_at,
    )


def _version_out(v: WorkflowVersion) -> schemas.WorkflowVersionOut:
    return schemas.WorkflowVersionOut(
        id=v.id, workflow_id=v.workflow_id, version=v.version, status=v.status,
        graph=v.graph, created_at=v.created_at,
    )


def _run_out(r: WorkflowRun) -> schemas.WorkflowRunOut:
    return schemas.WorkflowRunOut(
        id=r.id, workflow_version_id=r.workflow_version_id, status=r.status,
        current_node_id=r.current_node_id, variables=r.variables, error=r.error,
        started_at=r.started_at, completed_at=r.completed_at,
    )


def _budget_to_dict(b: AgentBudget) -> dict[str, Any]:
    return {
        "max_steps": b.max_steps, "max_tool_calls": b.max_tool_calls,
        "max_runtime_s": b.max_runtime_s, "max_cost_usd": b.max_cost_usd,
        "consumed_steps": b.consumed_steps, "consumed_tool_calls": b.consumed_tool_calls,
        "consumed_cost_usd": b.consumed_cost_usd, "tripped": b.tripped,
    }


def _budget_from_dict(d: dict[str, Any]) -> AgentBudget:
    """Reconstruct the budget a paused run left off with — resuming must inherit what was
    already spent (docs/17 §2 rule 3), not start a fresh ceiling."""
    b = default_budget()
    if not d:
        return b
    b.max_steps = d.get("max_steps", b.max_steps)
    b.max_tool_calls = d.get("max_tool_calls", b.max_tool_calls)
    b.max_runtime_s = d.get("max_runtime_s", b.max_runtime_s)
    b.max_cost_usd = d.get("max_cost_usd", b.max_cost_usd)
    b.consumed_steps = d.get("consumed_steps", 0)
    b.consumed_tool_calls = d.get("consumed_tool_calls", 0)
    b.consumed_cost_usd = d.get("consumed_cost_usd", 0.0)
    b.tripped = d.get("tripped")
    return b


async def _tool_executor_for(
    session: AsyncSession, ctx: OrgContext, agent_id: uuid.UUID | None
) -> Any:
    """A `WorkflowToolExecutor` over the same `Tool` rows chat's `run_turn` uses — reuses
    `execute_tool_call` rather than a second dispatch path. `None` when there is no agent to
    scope tools to, or the agent has no version yet — a tool node then fails cleanly per
    `graph.py`'s own handling rather than crashing on a `ToolContext.version` a builtin tool
    (e.g. `knowledge_search`, which reads `ctx.version.rag_config`) assumes is real.
    """
    if agent_id is None:
        return None
    agent = await session.get(Agent, agent_id)
    if agent is None or agent.current_version_id is None:
        return None
    version = await session.get(AgentVersion, agent.current_version_id)
    if version is None:
        return None
    _specs, by_name = await resolve_agent_tools(session, ctx.org.id, agent_id, include_mcp=True)
    tool_ctx = ToolContext(session=session, org_id=ctx.org.id, agent_id=agent_id, version=version)

    async def executor(name: str, args: dict[str, Any]) -> dict[str, Any]:
        call = ToolCall(id=str(uuid.uuid4()), name=name, arguments=args)
        res = await execute_tool_call(session, tool_ctx, by_name, call)
        return {"output": res.output, "status": res.status, "error": res.error}

    return executor


async def _agent_executor_for(session: AsyncSession, ctx: OrgContext) -> WorkflowAgentExecutor:
    """An `agent` node's executor: runs an existing published `Agent` through the real
    agentic runtime (`app.chat.runtime.run_turn`), a single non-streaming user turn with no
    conversation persistence — the workflow's own `WorkflowStep` for this node is the record
    of what happened, not a second `Conversation`/`Message` pair. Passes the SAME budget
    instance into `run_turn` so a nested think→act→observe cycle decrements the workflow
    run's own ceiling (docs/17 §2 rule 3), and disables the output guard/PII allowlist the
    same way the Playground does — the caller here is another workflow node, not a visitor,
    and the untrusted-output rule is enforced by `graph.py`'s `neutralize_injections()` on the
    return value instead.
    """

    async def executor(agent_id_str: str, message: str, budget: AgentBudget) -> dict[str, Any]:
        try:
            agent_id = uuid.UUID(agent_id_str)
        except ValueError:
            return {"content": "", "status": "error", "error": f"invalid agent_id {agent_id_str!r}"}
        agent = await session.get(Agent, agent_id)
        if agent is None or agent.organization_id != ctx.org.id:
            return {"content": "", "status": "error", "error": "agent not found"}
        if agent.current_version_id is None:
            return {"content": "", "status": "error", "error": "agent has no published version"}
        version = await session.get(AgentVersion, agent.current_version_id)
        if version is None:
            return {"content": "", "status": "error", "error": "agent has no published version"}

        mc = version.model_config_json or {}
        provider_name = mc.get("provider", "fake")
        try:
            provider = await get_chat_provider_chain(
                session, ctx.org.id, mc, agent_id=agent.id, resolve=get_chat_provider
            )
        except AppError as exc:
            log.warning("workflow_agent_node_provider_unavailable", agent_id=str(agent.id), error=str(exc))
            return {"content": "", "status": "error", "error": str(exc)}

        system_prompt = compose_system_prompt(
            version.system_prompt, version.persona, agent_name=agent.name, business_name=ctx.org.name,
            variables=chat_variables.build_context(agent_name=agent.name, business_name=ctx.org.name),
        )
        messages: list[Message] = []
        if system_prompt:
            messages.append(Message(role="system", content=system_prompt))
        messages.append(Message(role="user", content=message))
        req = ChatRequest(
            model=mc.get("model", provider_name), messages=messages,
            temperature=mc.get("temperature", 0.7), top_p=mc.get("top_p", 1.0),
            max_tokens=mc.get("max_tokens", 1024),
            frequency_penalty=mc.get("frequency_penalty", 0.0), presence_penalty=mc.get("presence_penalty", 0.0),
            stop=mc.get("stop") or None, stream=False,
        )
        result = TurnResult()
        async for _ev in run_turn(provider, req, [], result, budget=budget, guard_output=False):
            pass
        return {
            "content": result.content,
            "status": "error" if result.error else "completed",
            "error": result.error,
        }

    return executor


async def _sub_workflow_executor_for(session: AsyncSession, ctx: OrgContext) -> WorkflowSubExecutor:
    """A `sub_agent` node's executor: runs another org-owned, published `Workflow` in-process,
    sharing the same budget (call depth included). Deliberately does not persist a separate
    `WorkflowRun` row for the nested execution — the parent's own `WorkflowStep` for the
    `sub_agent` node already records the sanitized outcome; a full nested audit trail is a
    follow-up, not built this slice.
    """

    async def executor(
        workflow_id_str: str, variables_snapshot: dict[str, Any], budget: AgentBudget
    ) -> WorkflowRunResult:
        try:
            workflow_id = uuid.UUID(workflow_id_str)
        except ValueError:
            return WorkflowRunResult(
                status="failed", variables=variables_snapshot, error=f"invalid workflow_id {workflow_id_str!r}"
            )
        workflow = await session.get(Workflow, workflow_id)
        if workflow is None or workflow.organization_id != ctx.org.id or workflow.deleted_at is not None:
            return WorkflowRunResult(status="failed", variables=variables_snapshot, error="sub-workflow not found")
        if workflow.current_version_id is None:
            return WorkflowRunResult(
                status="failed", variables=variables_snapshot, error="sub-workflow has no published version"
            )
        version = await session.get(WorkflowVersion, workflow.current_version_id)
        assert version is not None

        nested_tool_executor = await _tool_executor_for(session, ctx, workflow.agent_id)
        nested_agent_executor = await _agent_executor_for(session, ctx)
        return await run_workflow(
            version.graph, variables=variables_snapshot, budget=budget,
            tool_executor=nested_tool_executor, agent_executor=nested_agent_executor,
            # Passing itself allows a chain deeper than one level — bounded by
            # `budget.max_call_depth`, not by how many executor factories were pre-built.
            sub_workflow_executor=executor,
        )

    return executor


async def _persist_steps(
    session: AsyncSession, run: WorkflowRun, result: WorkflowRunResult
) -> None:
    for step in result.steps:
        session.add(
            WorkflowStep(
                workflow_run_id=run.id, node_id=step["node_id"], node_type=step["node_type"],
                status=step["status"], input=step.get("input"), output=step.get("output"),
                latency_ms=step.get("latency_ms"), cost_usd=step.get("cost_usd"), error=step.get("error"),
            )
        )


# ── Workflow CRUD ────────────────────────────────────────────────────────────────────────


async def create_workflow(
    session: AsyncSession, ctx: OrgContext, agent_id: uuid.UUID | None, data: schemas.CreateWorkflowRequest
) -> schemas.WorkflowOut:
    rbac.require_permission(ctx.role, rbac.WORKFLOWS_WRITE)
    if agent_id is not None:
        agent = await session.get(Agent, agent_id)
        if agent is None or agent.organization_id != ctx.org.id:
            raise AppError("workflows.agent_not_found", "Agent not found.", 404)
    workflow = Workflow(
        organization_id=ctx.org.id, agent_id=agent_id, name=data.name, description=data.description,
        created_by=ctx.user.id,
    )
    session.add(workflow)
    await session.flush()
    return _workflow_out(workflow)


async def list_workflows(
    session: AsyncSession, ctx: OrgContext, agent_id: uuid.UUID | None
) -> list[schemas.WorkflowOut]:
    rbac.require_permission(ctx.role, rbac.READ)
    stmt = select(Workflow).where(Workflow.organization_id == ctx.org.id, Workflow.deleted_at.is_(None))
    if agent_id is not None:
        stmt = stmt.where(Workflow.agent_id == agent_id)
    rows = (await session.execute(stmt.order_by(Workflow.created_at.desc()))).scalars().all()
    return [_workflow_out(w) for w in rows]


async def get_workflow(session: AsyncSession, ctx: OrgContext, workflow_id: uuid.UUID) -> schemas.WorkflowOut:
    rbac.require_permission(ctx.role, rbac.READ)
    return _workflow_out(await _get_workflow(session, ctx, workflow_id))


async def update_workflow(
    session: AsyncSession, ctx: OrgContext, workflow_id: uuid.UUID, data: schemas.UpdateWorkflowRequest
) -> schemas.WorkflowOut:
    rbac.require_permission(ctx.role, rbac.WORKFLOWS_WRITE)
    workflow = await _get_workflow(session, ctx, workflow_id)
    if data.name is not None:
        workflow.name = data.name
    if data.description is not None:
        workflow.description = data.description
    return _workflow_out(workflow)


async def delete_workflow(session: AsyncSession, ctx: OrgContext, workflow_id: uuid.UUID) -> None:
    rbac.require_permission(ctx.role, rbac.WORKFLOWS_WRITE)
    workflow = await _get_workflow(session, ctx, workflow_id)

    workflow.deleted_at = dt.datetime.now(tz=dt.UTC)


# ── Versions ─────────────────────────────────────────────────────────────────────────────


async def create_version(
    session: AsyncSession, ctx: OrgContext, workflow_id: uuid.UUID, data: schemas.CreateWorkflowVersionRequest
) -> schemas.WorkflowVersionOut:
    rbac.require_permission(ctx.role, rbac.WORKFLOWS_WRITE)
    workflow = await _get_workflow(session, ctx, workflow_id)
    errors = validate_graph(data.graph)
    if errors:
        raise AppError("workflows.invalid_graph", "; ".join(errors), 400)
    stmt = select(WorkflowVersion.version).where(WorkflowVersion.workflow_id == workflow_id).order_by(
        WorkflowVersion.version.desc()
    )
    latest = (await session.execute(stmt)).scalars().first()
    version = WorkflowVersion(
        workflow_id=workflow.id, version=(latest or 0) + 1, status="draft", graph=data.graph,
        created_by=ctx.user.id,
    )
    session.add(version)
    await session.flush()
    return _version_out(version)


async def list_versions(
    session: AsyncSession, ctx: OrgContext, workflow_id: uuid.UUID
) -> list[schemas.WorkflowVersionOut]:
    rbac.require_permission(ctx.role, rbac.READ)
    await _get_workflow(session, ctx, workflow_id)
    stmt = select(WorkflowVersion).where(WorkflowVersion.workflow_id == workflow_id).order_by(
        WorkflowVersion.version.desc()
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [_version_out(v) for v in rows]


async def publish_version(
    session: AsyncSession, ctx: OrgContext, workflow_id: uuid.UUID, version: int
) -> schemas.WorkflowOut:
    rbac.require_permission(ctx.role, rbac.WORKFLOWS_PUBLISH)
    workflow = await _get_workflow(session, ctx, workflow_id)
    v = await _get_version(session, workflow_id, version)
    v.status = "published"
    workflow.current_version_id = v.id
    return _workflow_out(workflow)


# ── Execution ────────────────────────────────────────────────────────────────────────────


async def run_workflow_now(
    session: AsyncSession, ctx: OrgContext, workflow_id: uuid.UUID, data: schemas.RunWorkflowRequest
) -> schemas.WorkflowRunOut:
    """Runs the workflow's PUBLISHED version. Test-mode execution against a draft version is
    intentionally not built in this slice — see docs/PROGRESS.md's Phase 2 entry."""
    rbac.require_permission(ctx.role, rbac.WORKFLOWS_WRITE)
    workflow = await _get_workflow(session, ctx, workflow_id)
    if workflow.current_version_id is None:
        raise AppError("workflows.not_published", "This workflow has no published version.", 400)
    version = await session.get(WorkflowVersion, workflow.current_version_id)
    assert version is not None

    budget = default_budget()
    run = WorkflowRun(
        workflow_version_id=version.id, organization_id=ctx.org.id,
        conversation_id=data.conversation_id, status="running", variables=dict(data.variables),
        budget=_budget_to_dict(budget),
    )
    session.add(run)
    await session.flush()

    tool_executor = await _tool_executor_for(session, ctx, workflow.agent_id)
    agent_executor = await _agent_executor_for(session, ctx)
    sub_workflow_executor = await _sub_workflow_executor_for(session, ctx)
    result = await run_workflow(
        version.graph, variables=run.variables, budget=budget, tool_executor=tool_executor,
        agent_executor=agent_executor, sub_workflow_executor=sub_workflow_executor,
    )
    await _persist_steps(session, run, result)

    run.status = result.status
    run.current_node_id = result.current_node_id
    run.error = result.error
    run.budget = _budget_to_dict(budget)
    if result.status in ("completed", "failed", "budget_exceeded"):
        run.completed_at = dt.datetime.now(tz=dt.UTC)
    return _run_out(run)


async def resume_workflow_run(
    session: AsyncSession, ctx: OrgContext, run_id: uuid.UUID, data: schemas.ResumeWorkflowRequest
) -> schemas.WorkflowRunOut:
    rbac.require_permission(ctx.role, rbac.WORKFLOWS_WRITE)
    run = await _get_run(session, ctx, run_id)
    if run.status != "paused_approval":
        raise AppError("workflows.not_paused", "This run is not waiting on approval.", 400)
    version = await session.get(WorkflowVersion, run.workflow_version_id)
    assert version is not None
    workflow = await session.get(Workflow, version.workflow_id)
    assert workflow is not None

    budget = _budget_from_dict(run.budget)
    tool_executor = await _tool_executor_for(session, ctx, workflow.agent_id)
    agent_executor = await _agent_executor_for(session, ctx)
    sub_workflow_executor = await _sub_workflow_executor_for(session, ctx)
    result = await run_workflow(
        version.graph, variables=run.variables, budget=budget, tool_executor=tool_executor,
        agent_executor=agent_executor, sub_workflow_executor=sub_workflow_executor,
        start_node_id=run.current_node_id, resume_input={"decision": data.decision},
    )
    await _persist_steps(session, run, result)

    run.status = result.status
    run.current_node_id = result.current_node_id
    run.error = result.error
    run.budget = _budget_to_dict(budget)
    if result.status in ("completed", "failed", "budget_exceeded"):
        run.completed_at = dt.datetime.now(tz=dt.UTC)
    return _run_out(run)


async def cancel_workflow_run(session: AsyncSession, ctx: OrgContext, run_id: uuid.UUID) -> schemas.WorkflowRunOut:
    rbac.require_permission(ctx.role, rbac.WORKFLOWS_WRITE)
    run = await _get_run(session, ctx, run_id)
    if run.status in ("completed", "failed", "cancelled", "budget_exceeded"):
        return _run_out(run)
    run.status = "cancelled"
    run.completed_at = dt.datetime.now(tz=dt.UTC)
    return _run_out(run)


async def list_run_steps(
    session: AsyncSession, ctx: OrgContext, run_id: uuid.UUID
) -> list[schemas.WorkflowStepOut]:
    rbac.require_permission(ctx.role, rbac.READ)
    await _get_run(session, ctx, run_id)
    stmt = select(WorkflowStep).where(WorkflowStep.workflow_run_id == run_id).order_by(
        WorkflowStep.started_at.asc()
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [
        schemas.WorkflowStepOut(
            id=s.id, node_id=s.node_id, node_type=s.node_type, status=s.status, input=s.input,
            output=s.output, latency_ms=s.latency_ms, cost_usd=s.cost_usd, error=s.error,
            started_at=s.started_at,
        )
        for s in rows
    ]
