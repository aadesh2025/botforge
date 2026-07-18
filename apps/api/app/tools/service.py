"""Tool CRUD, resolution, execution dispatch, and the tool-run log."""

from __future__ import annotations

import time
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import rbac
from app.core.errors import AppError
from app.core.logging import get_logger
from app.integrations.n8n_client import get_client
from app.llm.types import ToolCall, ToolSpec
from app.models import Agent, AgentVersion, Tool, ToolRun
from app.modules.orgs.deps import OrgContext
from app.tools import schemas
from app.tools.base import ToolContext, ToolResult
from app.tools.builtins import BUILTINS
from app.tools.http_tool import execute_http_tool
from app.tools.n8n_tool import execute_n8n_tool

log = get_logger("tools")


# ── Built-in catalog ──────────────────────────────────────────────────────────────
def list_builtins() -> list[schemas.BuiltinToolOut]:
    return [
        schemas.BuiltinToolOut(name=b.name, description=b.description, parameters=b.parameters)
        for b in BUILTINS.values()
    ]


# ── CRUD ───────────────────────────────────────────────────────────────────────────
def _tool_out(tool: Tool) -> schemas.ToolOut:
    return schemas.ToolOut(
        id=tool.id,
        agent_id=tool.agent_id,
        name=tool.name,
        type=tool.type,
        description=tool.description,
        enabled=tool.enabled,
        config=tool.config,
        input_schema=tool.input_schema,
        created_at=tool.created_at,
    )


async def _get_tool(session: AsyncSession, ctx: OrgContext, tool_id: uuid.UUID) -> Tool:
    tool = await session.get(Tool, tool_id)
    if tool is None or tool.organization_id != ctx.org.id:
        raise AppError("tools.not_found", "Tool not found.", 404)
    return tool


async def create_tool(session: AsyncSession, ctx: OrgContext, data: schemas.CreateToolRequest) -> schemas.ToolOut:
    rbac.require_permission(ctx.role, rbac.TOOLS_MANAGE)
    description = data.description
    input_schema = data.input_schema
    config = data.config

    if data.type == "builtin":
        builtin = BUILTINS.get(data.name)
        if builtin is None:
            raise AppError("tools.unknown_builtin", f"Unknown built-in tool '{data.name}'.", 400)
        description = description or builtin.description
        input_schema = builtin.parameters  # always mirror the canonical schema
    elif not config.get("url"):
        raise AppError("tools.url_required", "HTTP tools require a config.url.", 400)

    tool = Tool(
        organization_id=ctx.org.id,
        agent_id=data.agent_id,
        name=data.name,
        type=data.type,
        description=description,
        enabled=data.enabled,
        config=config,
        input_schema=input_schema,
        created_by=ctx.user.id,
    )
    session.add(tool)
    await session.flush()
    return _tool_out(tool)


async def list_tools(session: AsyncSession, ctx: OrgContext, agent_id: uuid.UUID | None) -> list[schemas.ToolOut]:
    rbac.require_permission(ctx.role, rbac.READ)
    stmt = select(Tool).where(Tool.organization_id == ctx.org.id).order_by(Tool.created_at.desc())
    if agent_id is not None:
        stmt = stmt.where(Tool.agent_id == agent_id)
    return [_tool_out(t) for t in (await session.execute(stmt)).scalars().all()]


async def get_tool(session: AsyncSession, ctx: OrgContext, tool_id: uuid.UUID) -> schemas.ToolOut:
    rbac.require_permission(ctx.role, rbac.READ)
    return _tool_out(await _get_tool(session, ctx, tool_id))


async def update_tool(
    session: AsyncSession, ctx: OrgContext, tool_id: uuid.UUID, data: schemas.UpdateToolRequest
) -> schemas.ToolOut:
    rbac.require_permission(ctx.role, rbac.TOOLS_MANAGE)
    tool = await _get_tool(session, ctx, tool_id)
    if data.description is not None:
        tool.description = data.description
    if data.enabled is not None:
        tool.enabled = data.enabled
    if data.config is not None:
        tool.config = data.config
    if data.input_schema is not None and tool.type != "builtin":
        tool.input_schema = data.input_schema
    return _tool_out(tool)


async def delete_tool(session: AsyncSession, ctx: OrgContext, tool_id: uuid.UUID) -> None:
    rbac.require_permission(ctx.role, rbac.TOOLS_MANAGE)
    tool = await _get_tool(session, ctx, tool_id)
    await session.delete(tool)


# ── Resolution + execution ─────────────────────────────────────────────────────────
async def resolve_agent_tools(
    session: AsyncSession, org_id: uuid.UUID, agent_id: uuid.UUID
) -> tuple[list[ToolSpec], dict[str, Tool]]:
    """Return (ToolSpecs, name→Tool) for the agent's enabled tools."""
    stmt = select(Tool).where(
        Tool.organization_id == org_id, Tool.agent_id == agent_id, Tool.enabled.is_(True)
    )
    tools = list((await session.execute(stmt)).scalars().all())
    specs = [
        ToolSpec(name=t.name, description=t.description or "", parameters=t.input_schema or {})
        for t in tools
    ]
    return specs, {t.name: t for t in tools}


async def build_tooling(
    session: AsyncSession,
    ctx: OrgContext,
    agent: Agent,
    version: AgentVersion,
    conversation_id: uuid.UUID | None,
) -> tuple[list[ToolSpec], Any]:
    """Return (ToolSpecs, executor) for an agent's enabled tools, or ([], None) when disabled.

    `executor(call)` runs the tool and returns a plain dict {output, status, error} (the runtime
    stays decoupled from the tools package).
    """
    features = version.features or {}
    if not features.get("tools_enabled"):
        return [], None
    specs, by_name = await resolve_agent_tools(session, ctx.org.id, agent.id)
    if not specs:
        return [], None

    tool_ctx = ToolContext(
        session=session,
        org_id=ctx.org.id,
        agent_id=agent.id,
        version=version,
        conversation_id=conversation_id,
    )

    async def executor(call: ToolCall) -> dict[str, Any]:
        res = await execute_tool_call(session, tool_ctx, by_name, call)
        return {"output": res.output, "status": res.status, "error": res.error}

    return specs, executor


async def _dispatch(tool: Tool, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    if tool.type == "builtin":
        builtin = BUILTINS.get(tool.name)
        if builtin is None:
            return ToolResult(output={}, status="error", error=f"unknown built-in '{tool.name}'")
        return await builtin.run(ctx, args)
    if tool.type == "http":
        return await execute_http_tool(tool.config, args)
    if tool.type == "n8n":
        return await execute_n8n_tool(tool.config, args, ctx)
    return ToolResult(output={}, status="error", error=f"unsupported tool type '{tool.type}'")


async def execute_tool_call(
    session: AsyncSession,
    ctx: ToolContext,
    tools_by_name: dict[str, Tool],
    call: ToolCall,
) -> ToolResult:
    """Execute a model-requested tool call, logging a ToolRun. Never raises.

    The ToolRun is created (status ``pending``) *before* dispatch so async tools (n8n) can pass
    its id as a callback token; it's finalized afterwards (async tools stay ``pending`` until the
    callback resolves them).
    """
    tool = tools_by_name.get(call.name)
    if tool is None:
        return ToolResult(output={}, status="error", error=f"tool '{call.name}' is not available")

    run = ToolRun(
        organization_id=tool.organization_id,
        tool_id=tool.id,
        conversation_id=ctx.conversation_id,
        input=call.arguments,
        status="pending",
    )
    session.add(run)
    await session.flush()
    ctx.run_id = run.id

    t0 = time.perf_counter()
    try:
        result = await _dispatch(tool, ctx, call.arguments)
    except Exception as exc:  # a tool must never crash the turn
        result = ToolResult(output={}, status="error", error=str(exc))
        log.warning("tool_execute_error", tool=call.name, error=str(exc))
    run.latency_ms = int((time.perf_counter() - t0) * 1000)
    run.output = result.output
    run.status = result.status
    run.error = result.error
    return result


async def test_tool(
    session: AsyncSession, ctx: OrgContext, tool_id: uuid.UUID, data: schemas.TestToolRequest
) -> schemas.TestToolResponse:
    rbac.require_permission(ctx.role, rbac.TOOLS_MANAGE)
    tool = await _get_tool(session, ctx, tool_id)
    tool_ctx = await _tool_context_for(session, ctx, tool)
    t0 = time.perf_counter()
    try:
        result = await _dispatch(tool, tool_ctx, data.input)
    except Exception as exc:
        result = ToolResult(output={}, status="error", error=str(exc))
    latency_ms = int((time.perf_counter() - t0) * 1000)
    session.add(
        ToolRun(
            organization_id=tool.organization_id,
            tool_id=tool.id,
            input=data.input,
            output=result.output,
            status=result.status,
            latency_ms=latency_ms,
            error=result.error,
        )
    )
    return schemas.TestToolResponse(
        status=result.status, output=result.output, error=result.error, latency_ms=latency_ms
    )


async def _tool_context_for(session: AsyncSession, ctx: OrgContext, tool: Tool) -> ToolContext:
    """Build a ToolContext for a standalone test (knowledge_search needs a version)."""
    version: AgentVersion | None = None
    agent_id = tool.agent_id
    if agent_id is not None:
        stmt = (
            select(AgentVersion)
            .where(AgentVersion.agent_id == agent_id)
            .order_by(AgentVersion.version.desc())
            .limit(1)
        )
        version = (await session.execute(stmt)).scalar_one_or_none()
    if version is None:
        # A throwaway version object so schema-only tools (datetime/calculator/http) can run.
        version = AgentVersion(agent_id=agent_id or uuid.uuid4(), version=0, rag_config={})
    return ToolContext(
        session=session,
        org_id=ctx.org.id,
        agent_id=agent_id or (await _any_agent_id(session, ctx)),
        version=version,
    )


async def _any_agent_id(session: AsyncSession, ctx: OrgContext) -> uuid.UUID:
    stmt = select(Agent.id).where(Agent.organization_id == ctx.org.id).limit(1)
    found = (await session.execute(stmt)).scalar_one_or_none()
    return found or uuid.uuid4()


# ── n8n binding ────────────────────────────────────────────────────────────────────
async def list_n8n_workflows(session: AsyncSession, ctx: OrgContext) -> list[schemas.N8nWorkflowOut]:
    rbac.require_permission(ctx.role, rbac.READ)
    client = get_client()
    workflows = await client.list_workflows()
    out: list[schemas.N8nWorkflowOut] = []
    for wf in workflows:
        out.append(
            schemas.N8nWorkflowOut(
                id=str(wf.get("id")),
                name=str(wf.get("name", "workflow")),
                active=bool(wf.get("active", False)),
                webhook_url=client.extract_webhook_url(wf),
            )
        )
    return out


async def bind_n8n_workflow(
    session: AsyncSession, ctx: OrgContext, data: schemas.BindN8nRequest
) -> schemas.ToolOut:
    rbac.require_permission(ctx.role, rbac.TOOLS_MANAGE)
    client = get_client()
    webhook_url = data.webhook_url
    workflow_name = data.workflow_name
    if not webhook_url and data.workflow_id:
        workflow = await client.get_workflow(data.workflow_id)
        workflow_name = workflow_name or str(workflow.get("name", ""))
        webhook_url = client.extract_webhook_url(workflow)
    if not webhook_url:
        raise AppError("tools.n8n_no_webhook", "Could not resolve a webhook URL for this workflow.", 400)

    input_schema = data.input_schema or {
        "type": "object",
        "properties": {"args": {"type": "object", "description": "arguments passed to the workflow"}},
    }
    tool = Tool(
        organization_id=ctx.org.id,
        agent_id=data.agent_id,
        name=data.name,
        type="n8n",
        description=data.description or f"n8n workflow: {workflow_name or data.workflow_id}",
        enabled=True,
        config={
            "workflow_id": data.workflow_id,
            "workflow_name": workflow_name,
            "webhook_url": webhook_url,
            "mode": data.mode,
        },
        input_schema=input_schema,
        created_by=ctx.user.id,
    )
    session.add(tool)
    await session.flush()
    return _tool_out(tool)


async def resolve_n8n_callback(
    session: AsyncSession, run_id: uuid.UUID, output: dict[str, Any], status: str, error: str | None
) -> bool:
    """Resolve a pending async n8n tool run from a verified callback. Returns True if updated."""
    run = await session.get(ToolRun, run_id)
    if run is None:
        return False
    run.output = output
    run.status = status
    run.error = error
    return True


async def list_runs(
    session: AsyncSession, ctx: OrgContext, conversation_id: uuid.UUID | None
) -> list[schemas.ToolRunOut]:
    rbac.require_permission(ctx.role, rbac.READ)
    stmt = (
        select(ToolRun)
        .where(ToolRun.organization_id == ctx.org.id)
        .order_by(ToolRun.created_at.desc())
        .limit(200)
    )
    if conversation_id is not None:
        stmt = stmt.where(ToolRun.conversation_id == conversation_id)
    return [
        schemas.ToolRunOut(
            id=r.id,
            tool_id=r.tool_id,
            conversation_id=r.conversation_id,
            status=r.status,
            input=r.input,
            output=r.output,
            latency_ms=r.latency_ms,
            error=r.error,
            created_at=r.created_at,
        )
        for r in (await session.execute(stmt)).scalars().all()
    ]
