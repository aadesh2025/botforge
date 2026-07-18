"""Agents & versions service, plus the playground chat runtime (no RAG yet)."""

from __future__ import annotations

import datetime as dt
import re
import secrets
import uuid
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat.runtime import ToolExecutor, TurnResult, run_turn
from app.core import rbac
from app.core.config import settings
from app.core.errors import AppError
from app.core.logging import get_logger
from app.llm.base import ChatProvider
from app.llm.fake import FakeChatProvider
from app.llm.registry import get_chat_provider
from app.llm.types import ChatRequest, Message
from app.models import Agent, AgentVersion
from app.modules.agents import schemas
from app.modules.orgs.deps import OrgContext
from app.rag.agent_retrieval import retrieve_for_version
from app.rag.retrieval import Citation
from app.tools.service import build_tooling

log = get_logger("agents")

DEFAULT_MODEL_CONFIG = {
    "provider": "groq",
    "model": "llama-3.3-70b-versatile",
    "temperature": 0.7,
    "top_p": 1.0,
    "max_tokens": 1024,
    "frequency_penalty": 0.0,
    "presence_penalty": 0.0,
    "stop": [],
}
DEFAULT_RAG_CONFIG = {"enabled": False, "knowledge_base_ids": [], "top_k": 5, "score_threshold": 0.7, "hybrid": True}
DEFAULT_FEATURES = {"tools_enabled": False, "memory_enabled": True, "handoff_enabled": False}


def _public_key() -> str:
    return f"bf_pub_{secrets.token_urlsafe(16)}"


def _slug_base(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "agent"


async def _unique_slug(session: AsyncSession, org_id: uuid.UUID, name: str) -> str:
    base = _slug_base(name)
    candidate, n = base, 1
    while True:
        exists = (
            await session.execute(
                select(Agent.id).where(Agent.organization_id == org_id, Agent.slug == candidate)
            )
        ).scalar_one_or_none()
        if exists is None:
            return candidate
        n += 1
        candidate = f"{base}-{n}"


async def _get_agent(session: AsyncSession, ctx: OrgContext, agent_id: uuid.UUID) -> Agent:
    agent = await session.get(Agent, agent_id)
    if agent is None or agent.organization_id != ctx.org.id or agent.deleted_at is not None:
        raise AppError("agents.not_found", "Agent not found.", 404)
    return agent


async def _latest_version(session: AsyncSession, agent_id: uuid.UUID) -> AgentVersion:
    stmt = (
        select(AgentVersion)
        .where(AgentVersion.agent_id == agent_id)
        .order_by(AgentVersion.version.desc())
        .limit(1)
    )
    version = (await session.execute(stmt)).scalar_one_or_none()
    if version is None:
        raise AppError("agents.no_version", "Agent has no versions.", 500)
    return version


async def _get_version(session: AsyncSession, agent_id: uuid.UUID, number: int) -> AgentVersion:
    stmt = select(AgentVersion).where(
        AgentVersion.agent_id == agent_id, AgentVersion.version == number
    )
    version = (await session.execute(stmt)).scalar_one_or_none()
    if version is None:
        raise AppError("agents.version_not_found", "Version not found.", 404)
    return version


async def _agent_out(session: AsyncSession, agent: Agent) -> schemas.AgentOut:
    draft = await _latest_version(session, agent.id)
    return schemas.AgentOut(
        id=agent.id,
        name=agent.name,
        slug=agent.slug,
        description=agent.description,
        status=agent.status,
        public_key=agent.public_key,
        is_public=agent.is_public,
        current_version_id=agent.current_version_id,
        draft_version=draft.version,
        created_at=agent.created_at,
        updated_at=agent.updated_at,
    )


def _version_out(v: AgentVersion) -> schemas.VersionOut:
    return schemas.VersionOut(
        id=v.id,
        version=v.version,
        is_published=v.is_published,
        system_prompt=v.system_prompt,
        persona=v.persona,
        welcome_message=v.welcome_message,
        fallback_message=v.fallback_message,
        suggested_prompts=v.suggested_prompts,
        llm_config=v.model_config_json,
        rag_config=v.rag_config,
        features=v.features,
        created_at=v.created_at,
    )


# ── Agent CRUD ────────────────────────────────────────────────────────────────
async def create_agent(session: AsyncSession, ctx: OrgContext, data: schemas.CreateAgentRequest) -> schemas.AgentOut:
    rbac.require_permission(ctx.role, rbac.AGENTS_WRITE)
    agent = Agent(
        organization_id=ctx.org.id,
        name=data.name,
        slug=await _unique_slug(session, ctx.org.id, data.name),
        description=data.description,
        status="draft",
        public_key=_public_key(),
        created_by=ctx.user.id,
    )
    session.add(agent)
    await session.flush()
    session.add(
        AgentVersion(
            agent_id=agent.id,
            version=1,
            is_published=False,
            welcome_message="Hi! How can I help you today?",
            fallback_message="I'm not sure about that — want me to connect you with a teammate?",
            suggested_prompts=[],
            persona={},
            model_config_json=dict(DEFAULT_MODEL_CONFIG),
            rag_config=dict(DEFAULT_RAG_CONFIG),
            features=dict(DEFAULT_FEATURES),
            created_by=ctx.user.id,
        )
    )
    await session.flush()
    return await _agent_out(session, agent)


async def list_agents(session: AsyncSession, ctx: OrgContext) -> list[schemas.AgentOut]:
    rbac.require_permission(ctx.role, rbac.READ)
    stmt = (
        select(Agent)
        .where(Agent.organization_id == ctx.org.id, Agent.deleted_at.is_(None))
        .order_by(Agent.created_at.desc())
    )
    agents = (await session.execute(stmt)).scalars().all()
    return [await _agent_out(session, a) for a in agents]


async def get_agent(session: AsyncSession, ctx: OrgContext, agent_id: uuid.UUID) -> schemas.AgentOut:
    rbac.require_permission(ctx.role, rbac.READ)
    return await _agent_out(session, await _get_agent(session, ctx, agent_id))


async def update_agent(
    session: AsyncSession, ctx: OrgContext, agent_id: uuid.UUID, data: schemas.UpdateAgentRequest
) -> schemas.AgentOut:
    rbac.require_permission(ctx.role, rbac.AGENTS_WRITE)
    agent = await _get_agent(session, ctx, agent_id)
    if data.name is not None:
        agent.name = data.name
    if data.description is not None:
        agent.description = data.description
    if data.is_public is not None:
        agent.is_public = data.is_public
    if data.status is not None:
        agent.status = data.status
    return await _agent_out(session, agent)


async def delete_agent(session: AsyncSession, ctx: OrgContext, agent_id: uuid.UUID) -> None:
    rbac.require_permission(ctx.role, rbac.AGENTS_WRITE)
    agent = await _get_agent(session, ctx, agent_id)
    agent.deleted_at = dt.datetime.now(tz=dt.UTC)


async def duplicate_agent(session: AsyncSession, ctx: OrgContext, agent_id: uuid.UUID) -> schemas.AgentOut:
    rbac.require_permission(ctx.role, rbac.AGENTS_WRITE)
    source = await _get_agent(session, ctx, agent_id)
    src_version = await _latest_version(session, source.id)
    clone = Agent(
        organization_id=ctx.org.id,
        name=f"{source.name} (copy)",
        slug=await _unique_slug(session, ctx.org.id, f"{source.name}-copy"),
        description=source.description,
        status="draft",
        public_key=_public_key(),
        created_by=ctx.user.id,
    )
    session.add(clone)
    await session.flush()
    session.add(
        AgentVersion(
            agent_id=clone.id,
            version=1,
            is_published=False,
            system_prompt=src_version.system_prompt,
            persona=dict(src_version.persona),
            welcome_message=src_version.welcome_message,
            fallback_message=src_version.fallback_message,
            suggested_prompts=list(src_version.suggested_prompts),
            model_config_json=dict(src_version.model_config_json),
            rag_config=dict(src_version.rag_config),
            features=dict(src_version.features),
            created_by=ctx.user.id,
        )
    )
    await session.flush()
    return await _agent_out(session, clone)


# ── Versions ──────────────────────────────────────────────────────────────────
async def list_versions(session: AsyncSession, ctx: OrgContext, agent_id: uuid.UUID) -> list[schemas.VersionOut]:
    rbac.require_permission(ctx.role, rbac.READ)
    await _get_agent(session, ctx, agent_id)
    stmt = select(AgentVersion).where(AgentVersion.agent_id == agent_id).order_by(AgentVersion.version.desc())
    return [_version_out(v) for v in (await session.execute(stmt)).scalars().all()]


async def _draft_from_latest(session: AsyncSession, agent_id: uuid.UUID, user_id: uuid.UUID) -> AgentVersion:
    """Create a new draft version copied from the latest version. Returns the ORM object."""
    latest = await _latest_version(session, agent_id)
    draft = AgentVersion(
        agent_id=agent_id,
        version=latest.version + 1,
        is_published=False,
        system_prompt=latest.system_prompt,
        persona=dict(latest.persona),
        welcome_message=latest.welcome_message,
        fallback_message=latest.fallback_message,
        suggested_prompts=list(latest.suggested_prompts),
        model_config_json=dict(latest.model_config_json),
        rag_config=dict(latest.rag_config),
        features=dict(latest.features),
        created_by=user_id,
    )
    session.add(draft)
    await session.flush()
    return draft


async def create_version(session: AsyncSession, ctx: OrgContext, agent_id: uuid.UUID) -> schemas.VersionOut:
    rbac.require_permission(ctx.role, rbac.AGENTS_WRITE)
    await _get_agent(session, ctx, agent_id)
    return _version_out(await _draft_from_latest(session, agent_id, ctx.user.id))


def _apply_version_patch(version: AgentVersion, data: schemas.UpdateVersionRequest) -> None:
    if data.system_prompt is not None:
        version.system_prompt = data.system_prompt
    if data.persona is not None:
        version.persona = data.persona
    if data.welcome_message is not None:
        version.welcome_message = data.welcome_message
    if data.fallback_message is not None:
        version.fallback_message = data.fallback_message
    if data.suggested_prompts is not None:
        version.suggested_prompts = data.suggested_prompts
    if data.llm_config is not None:
        version.model_config_json = data.llm_config
    if data.rag_config is not None:
        version.rag_config = data.rag_config
    if data.features is not None:
        version.features = data.features


async def update_version(
    session: AsyncSession,
    ctx: OrgContext,
    agent_id: uuid.UUID,
    number: int,
    data: schemas.UpdateVersionRequest,
) -> schemas.VersionOut:
    rbac.require_permission(ctx.role, rbac.AGENTS_WRITE)
    await _get_agent(session, ctx, agent_id)
    version = await _get_version(session, agent_id, number)
    if version.is_published:
        # Branch-on-edit (ADR-023): a published version is immutable, so the first edit
        # transparently forks a new draft copied from the latest version and patches that.
        # The response carries the new (higher) version number so the client can re-target.
        version = await _draft_from_latest(session, agent_id, ctx.user.id)
        log.info("branch_on_edit", agent_id=str(agent_id), new_version=version.version)
    _apply_version_patch(version, data)
    return _version_out(version)


async def publish_version(session: AsyncSession, ctx: OrgContext, agent_id: uuid.UUID, number: int) -> schemas.AgentOut:
    rbac.require_permission(ctx.role, rbac.AGENTS_WRITE)
    agent = await _get_agent(session, ctx, agent_id)
    version = await _get_version(session, agent_id, number)
    version.is_published = True
    agent.current_version_id = version.id
    agent.status = "published"
    return await _agent_out(session, agent)


async def rollback(session: AsyncSession, ctx: OrgContext, agent_id: uuid.UUID, number: int) -> schemas.AgentOut:
    rbac.require_permission(ctx.role, rbac.AGENTS_WRITE)
    agent = await _get_agent(session, ctx, agent_id)
    version = await _get_version(session, agent_id, number)
    if not version.is_published:
        raise AppError("agents.rollback_unpublished", "Can only roll back to a published version.", 400)
    agent.current_version_id = version.id
    agent.status = "published"
    return await _agent_out(session, agent)


# ── Playground (uses the draft version + LLM layer + RAG) ──────────────────────
async def _retrieve_context(
    session: AsyncSession, ctx: OrgContext, version: AgentVersion, query: str
) -> tuple[str, list[Citation]]:
    return await retrieve_for_version(session, ctx.org.id, version, query)


def _build_request(
    version: AgentVersion,
    data: schemas.PlaygroundRequest,
    stream: bool,
    context_block: str = "",
) -> ChatRequest:
    mc = version.model_config_json or {}
    messages: list[Message] = []
    if version.system_prompt:
        messages.append(Message(role="system", content=version.system_prompt))
    if context_block:
        messages.append(Message(role="system", content=context_block))
    for turn in data.history or []:
        messages.append(Message(role=turn.role, content=turn.content))
    messages.append(Message(role="user", content=data.message))
    return ChatRequest(
        model=mc.get("model", "fake-1"),
        messages=messages,
        temperature=mc.get("temperature", 0.7),
        top_p=mc.get("top_p", 1.0),
        max_tokens=mc.get("max_tokens", 1024),
        frequency_penalty=mc.get("frequency_penalty", 0.0),
        presence_penalty=mc.get("presence_penalty", 0.0),
        stop=mc.get("stop") or None,
        stream=stream,
    )


async def _resolve_playground_provider(
    session: AsyncSession, ctx: OrgContext, agent: Agent, provider: str
) -> ChatProvider:
    try:
        return await get_chat_provider(session, ctx.org.id, provider, agent_id=agent.id)
    except AppError:
        # No key configured → stub with the fake provider so the build isn't blocked (CLAUDE §7).
        log.warning("playground_stub_provider", provider=provider, agent_id=str(agent.id))
        return FakeChatProvider()


async def _playground_tooling(
    session: AsyncSession, ctx: OrgContext, agent: Agent, version: AgentVersion, provider: ChatProvider
) -> tuple[list[Any], ToolExecutor | None]:
    specs, executor = await build_tooling(session, ctx, agent, version, None)
    if specs and executor is not None and provider.supports_tools():
        return specs, executor
    return [], None


async def playground_stream(
    session: AsyncSession, ctx: OrgContext, agent_id: uuid.UUID, data: schemas.PlaygroundRequest
) -> AsyncIterator[str]:
    rbac.require_permission(ctx.role, rbac.AGENTS_WRITE)
    agent = await _get_agent(session, ctx, agent_id)
    version = await _latest_version(session, agent.id)
    provider_name = (version.model_config_json or {}).get("provider", "fake")
    provider = await _resolve_playground_provider(session, ctx, agent, provider_name)
    context_block, citations = await _retrieve_context(session, ctx, version, data.message)
    req = _build_request(version, data, stream=True, context_block=context_block)
    specs, executor = await _playground_tooling(session, ctx, agent, version, provider)
    if specs:
        req.tools = specs
    result = TurnResult()
    async for ev in run_turn(
        provider, req, [c.model_dump(mode="json") for c in citations], result,
        executor=executor, max_iters=settings.tool_max_iterations,
    ):
        yield f"data: {ev.model_dump_json()}\n\n"


async def playground_once(
    session: AsyncSession, ctx: OrgContext, agent_id: uuid.UUID, data: schemas.PlaygroundRequest
) -> dict[str, Any]:
    rbac.require_permission(ctx.role, rbac.AGENTS_WRITE)
    agent = await _get_agent(session, ctx, agent_id)
    version = await _latest_version(session, agent.id)
    provider_name = (version.model_config_json or {}).get("provider", "fake")
    provider = await _resolve_playground_provider(session, ctx, agent, provider_name)
    context_block, citations = await _retrieve_context(session, ctx, version, data.message)
    req = _build_request(version, data, stream=False, context_block=context_block)
    specs, executor = await _playground_tooling(session, ctx, agent, version, provider)
    if specs:
        req.tools = specs
    result = TurnResult()
    async for _ev in run_turn(
        provider, req, [c.model_dump(mode="json") for c in citations], result,
        executor=executor, max_iters=settings.tool_max_iterations,
    ):
        pass
    if result.error:
        raise AppError("llm.provider_error", result.error, 502)
    return {
        "content": result.content.strip(),
        "citations": result.citations,
        "tool_runs": result.tool_runs,
        "provider": result.provider,
        "model": result.model,
        "usage": {"prompt_tokens": result.prompt_tokens, "completion_tokens": result.completion_tokens},
    }


async def agent_count(session: AsyncSession, org_id: uuid.UUID) -> int:
    stmt = select(func.count()).select_from(Agent).where(
        Agent.organization_id == org_id, Agent.deleted_at.is_(None)
    )
    return int((await session.execute(stmt)).scalar_one())
