"""Workflow CRUD, versioning, and execution (docs/17 Phase 2).

Execution runs on Celery in production (docs/17 Phase 2 item 2): `run_workflow_now` /
`resume_workflow_run` create/update the `WorkflowRun` row, then `_dispatch_run` either enqueues
`app.worker.tasks.run_workflow_task` / `resume_workflow_run_task` — which call
`execute_queued_run` on the worker's own DB session — or, when `settings.celery_task_always_eager`
is set, run the SAME execution coroutine in-process instead of going through Celery at all. That
in-process branch exists for the same reason `app.core.email.queue_email` has one: every task in
`app.worker.tasks` drives its coroutine with `asyncio.run()`, which raises inside a loop that is
already running — exactly what a request handler's event loop is. Going through Celery's own
"eager" machinery here would hit that trap; bypassing it entirely does not. See CLAUDE.md §12.

The `WorkflowRun` row is the resumability boundary regardless of path — `variables`/`budget`/
`current_node_id` are always read back from the DB, never kept in Python process memory across a
pause, which is what makes "which process runs this" a detail the execution logic itself doesn't
need to know about.

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
from app.core.config import settings
from app.core.errors import AppError
from app.core.logging import get_logger
from app.llm.registry import get_chat_provider, get_chat_provider_chain
from app.llm.types import ChatRequest, Message, ToolCall
from app.models import (
    Agent,
    AgentVersion,
    Organization,
    Workflow,
    WorkflowRun,
    WorkflowStep,
    WorkflowVersion,
)
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


async def _latest_workflow_version(session: AsyncSession, workflow_id: uuid.UUID) -> WorkflowVersion:
    """The version a "Test run" exercises — draft or published, whichever was created most
    recently. Mirrors `app.modules.agents.service._latest_version`'s semantics for the Agent
    Playground exactly: an operator testing wants to see what they just saved, not necessarily
    what's live."""
    stmt = (
        select(WorkflowVersion)
        .where(WorkflowVersion.workflow_id == workflow_id)
        .order_by(WorkflowVersion.version.desc())
        .limit(1)
    )
    version = (await session.execute(stmt)).scalar_one_or_none()
    if version is None:
        raise AppError("workflows.no_version", "This workflow has no versions yet.", 400)
    return version


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
        started_at=r.started_at, completed_at=r.completed_at, is_test=r.is_test,
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
    session: AsyncSession, org: Organization, agent_id: uuid.UUID | None
) -> Any:
    """A `WorkflowToolExecutor` over the same `Tool` rows chat's `run_turn` uses — reuses
    `execute_tool_call` rather than a second dispatch path. `None` when there is no agent to
    scope tools to, or the agent has no version yet — a tool node then fails cleanly per
    `graph.py`'s own handling rather than crashing on a `ToolContext.version` a builtin tool
    (e.g. `knowledge_search`, which reads `ctx.version.rag_config`) assumes is real.

    Takes `org: Organization`, not a full `OrgContext` — a Celery worker process has no HTTP
    request to build one from, only the `organization_id` a `WorkflowRun` row carries. The
    RBAC-checked callers (`run_workflow_now` etc.) still take `OrgContext`; only the pure
    execution layer was narrowed to what it actually uses.
    """
    if agent_id is None:
        return None
    agent = await session.get(Agent, agent_id)
    if agent is None or agent.current_version_id is None:
        return None
    version = await session.get(AgentVersion, agent.current_version_id)
    if version is None:
        return None
    _specs, by_name = await resolve_agent_tools(session, org.id, agent_id, include_mcp=True)
    tool_ctx = ToolContext(session=session, org_id=org.id, agent_id=agent_id, version=version)

    async def executor(name: str, args: dict[str, Any]) -> dict[str, Any]:
        call = ToolCall(id=str(uuid.uuid4()), name=name, arguments=args)
        res = await execute_tool_call(session, tool_ctx, by_name, call)
        return {"output": res.output, "status": res.status, "error": res.error}

    return executor


async def _agent_executor_for(session: AsyncSession, org: Organization) -> WorkflowAgentExecutor:
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
        if agent is None or agent.organization_id != org.id:
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
                session, org.id, mc, agent_id=agent.id, resolve=get_chat_provider
            )
        except AppError as exc:
            log.warning("workflow_agent_node_provider_unavailable", agent_id=str(agent.id), error=str(exc))
            return {"content": "", "status": "error", "error": str(exc)}

        system_prompt = compose_system_prompt(
            version.system_prompt, version.persona, agent_name=agent.name, business_name=org.name,
            variables=chat_variables.build_context(agent_name=agent.name, business_name=org.name),
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


async def _sub_workflow_executor_for(session: AsyncSession, org: Organization) -> WorkflowSubExecutor:
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
        if workflow is None or workflow.organization_id != org.id or workflow.deleted_at is not None:
            return WorkflowRunResult(status="failed", variables=variables_snapshot, error="sub-workflow not found")
        if workflow.current_version_id is None:
            return WorkflowRunResult(
                status="failed", variables=variables_snapshot, error="sub-workflow has no published version"
            )
        version = await session.get(WorkflowVersion, workflow.current_version_id)
        assert version is not None

        nested_tool_executor = await _tool_executor_for(session, org, workflow.agent_id)
        nested_agent_executor = await _agent_executor_for(session, org)
        return await run_workflow(
            version.graph, variables=variables_snapshot, budget=budget,
            tool_executor=nested_tool_executor, agent_executor=nested_agent_executor,
            # Passing itself allows a chain deeper than one level — bounded by
            # `budget.max_call_depth`, not by how many executor factories were pre-built.
            sub_workflow_executor=executor,
        )

    return executor


async def _persist_one_step(
    session: AsyncSession, run: WorkflowRun, step: dict[str, Any], *, commit: bool
) -> None:
    session.add(
        WorkflowStep(
            workflow_run_id=run.id, node_id=step["node_id"], node_type=step["node_type"],
            status=step["status"], input=step.get("input"), output=step.get("output"),
            latency_ms=step.get("latency_ms"), cost_usd=step.get("cost_usd"), error=step.get("error"),
        )
    )
    await session.flush()
    if commit:
        # Durable immediately — so `GET .../steps` polled from a DIFFERENT connection (the
        # API request serving that poll) sees progress on a long-running run while the Celery
        # task is still executing it, not only once the whole run finishes. Only ever true on
        # the worker's own dedicated session (see `execute_queued_run`) — never on a
        # request-scoped session, which the test harness shares across a whole test inside one
        # uncommitted transaction (`tests/conftest.py`); committing there would break that
        # isolation, which is exactly why `commit` is plumbed through rather than hardcoded.
        await session.commit()


async def _execute_and_persist(
    session: AsyncSession,
    run: WorkflowRun,
    workflow: Workflow,
    version: WorkflowVersion,
    *,
    resume_input: dict[str, Any] | None = None,
    commit_each_step: bool = False,
) -> WorkflowRunResult:
    """The one execution path both the in-process (eager) and Celery-task dispatch routes call
    — `_dispatch_run` decides WHICH process runs this, not what it does once it does.
    """
    org = await session.get(Organization, run.organization_id)
    assert org is not None
    budget = _budget_from_dict(run.budget)
    tool_executor = await _tool_executor_for(session, org, workflow.agent_id)
    agent_executor = await _agent_executor_for(session, org)
    sub_workflow_executor = await _sub_workflow_executor_for(session, org)

    async def on_step(step: dict[str, Any]) -> None:
        await _persist_one_step(session, run, step, commit=commit_each_step)

    result = await run_workflow(
        version.graph, variables=run.variables, budget=budget, tool_executor=tool_executor,
        agent_executor=agent_executor, sub_workflow_executor=sub_workflow_executor,
        start_node_id=run.current_node_id if resume_input is not None else None,
        resume_input=resume_input, on_step=on_step,
    )
    run.status = result.status
    run.current_node_id = result.current_node_id
    run.error = result.error
    run.budget = _budget_to_dict(budget)
    if result.status in ("completed", "failed", "budget_exceeded"):
        run.completed_at = dt.datetime.now(tz=dt.UTC)
    await session.flush()
    if commit_each_step:
        await session.commit()
    return result


async def _dispatch_run(
    session: AsyncSession,
    run: WorkflowRun,
    workflow: Workflow,
    version: WorkflowVersion,
    *,
    resume_input: dict[str, Any] | None = None,
) -> None:
    """Runs `_execute_and_persist` in-process when Celery is in eager mode (see the module
    docstring for why that must NOT go through Celery's own eager machinery), otherwise
    enqueues a Celery task and returns immediately — the caller's `WorkflowRun` stays in
    `"running"` until that task updates it.
    """
    if settings.celery_task_always_eager:
        await _execute_and_persist(session, run, workflow, version, resume_input=resume_input)
        return
    # Deliberately no explicit commit before enqueueing here — matches the existing
    # `enqueue_document_ingestion` convention (flush, then `.delay()`) rather than introducing
    # a stricter guarantee only for workflows. A worker that picks up this task before the
    # enclosing request's `get_session()` commit lands would find no row; unobserved in
    # practice so far for ingestion, and the same trade-off applies here. See docs/PROGRESS.md.
    from app.worker.tasks import resume_workflow_run_task, run_workflow_task

    if resume_input is None:
        run_workflow_task.delay(str(run.id))
    else:
        resume_workflow_run_task.delay(str(run.id), resume_input.get("decision", "rejected"))


async def execute_queued_run(
    session: AsyncSession, run_id: uuid.UUID, *, resume_decision: str | None = None
) -> str:
    """Entry point for the Celery task (`app.worker.tasks.run_workflow_task` /
    `resume_workflow_run_task`). No RBAC check and no `OrgContext` — the request that enqueued
    this already checked `WORKFLOWS_WRITE`, and a worker process has no HTTP request to build
    one from; this loads only what execution itself needs.
    """
    run = await session.get(WorkflowRun, run_id)
    if run is None:
        log.error("workflow_run_vanished", run_id=str(run_id))
        return "not_found"
    version = await session.get(WorkflowVersion, run.workflow_version_id)
    if version is None:
        run.status = "failed"
        run.error = "workflow version was deleted before this run could execute"
        run.completed_at = dt.datetime.now(tz=dt.UTC)
        return run.status
    workflow = await session.get(Workflow, version.workflow_id)
    if workflow is None:
        run.status = "failed"
        run.error = "workflow was deleted before this run could execute"
        run.completed_at = dt.datetime.now(tz=dt.UTC)
        return run.status
    resume_input = {"decision": resume_decision} if resume_decision is not None else None
    result = await _execute_and_persist(
        session, run, workflow, version, resume_input=resume_input, commit_each_step=True
    )
    return result.status


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


async def _create_and_dispatch_run(
    session: AsyncSession,
    ctx: OrgContext,
    workflow: Workflow,
    version: WorkflowVersion,
    data: schemas.RunWorkflowRequest,
    *,
    is_test: bool,
) -> schemas.WorkflowRunOut:
    run = WorkflowRun(
        workflow_version_id=version.id, organization_id=ctx.org.id,
        conversation_id=data.conversation_id, status="running", variables=dict(data.variables),
        budget=_budget_to_dict(default_budget()), is_test=is_test,
    )
    session.add(run)
    await session.flush()
    await _dispatch_run(session, run, workflow, version)
    return _run_out(run)


async def run_workflow_now(
    session: AsyncSession, ctx: OrgContext, workflow_id: uuid.UUID, data: schemas.RunWorkflowRequest
) -> schemas.WorkflowRunOut:
    """Runs the workflow's PUBLISHED version. Creates the `WorkflowRun` row and dispatches
    execution (Celery in production; see `_dispatch_run`) — this function itself never walks
    the graph. `run.status` is still `"running"` in the returned `WorkflowRunOut` when
    dispatched to a real worker; only eager/test mode finishes before this returns.

    Test-mode execution against the latest (possibly unpublished) version is
    `run_workflow_test` below, on a separate endpoint.
    """
    rbac.require_permission(ctx.role, rbac.WORKFLOWS_WRITE)
    workflow = await _get_workflow(session, ctx, workflow_id)
    if workflow.current_version_id is None:
        raise AppError("workflows.not_published", "This workflow has no published version.", 400)
    version = await session.get(WorkflowVersion, workflow.current_version_id)
    assert version is not None
    return await _create_and_dispatch_run(session, ctx, workflow, version, data, is_test=False)


async def run_workflow_test(
    session: AsyncSession, ctx: OrgContext, workflow_id: uuid.UUID, data: schemas.RunWorkflowRequest
) -> schemas.WorkflowRunOut:
    """Runs the workflow's LATEST version — draft or published — so an editor can try out what
    they just saved before anyone with `WORKFLOWS_PUBLISH` needs to sign off on it. Requires
    only `WORKFLOWS_WRITE`, deliberately: testing your own draft is part of authoring it, not a
    publish action (docs/17 Phase 2 item 3). Marked `is_test=True`; otherwise executed through
    the exact same dispatch path as a real run — no side-effect sandboxing, the same trade-off
    the Agent Playground already makes.
    """
    rbac.require_permission(ctx.role, rbac.WORKFLOWS_WRITE)
    workflow = await _get_workflow(session, ctx, workflow_id)
    version = await _latest_workflow_version(session, workflow_id)
    return await _create_and_dispatch_run(session, ctx, workflow, version, data, is_test=True)


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

    # Reflects the decision was accepted immediately, before a real worker picks it up —
    # a poller must never see the stale "paused_approval" once a decision has been made.
    run.status = "running"
    await session.flush()
    await _dispatch_run(session, run, workflow, version, resume_input={"decision": data.decision})
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
