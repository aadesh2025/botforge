"""Public (widget) config + chat runtime — no dashboard auth, keyed by public_key.

Reuses the dashboard chat building blocks (assembly, retrieval, tools, run_turn, persistence);
resolves the agent/org from its ``public_key`` instead of an OrgContext.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat.assembly import build_messages
from app.chat.runtime import TurnResult, run_turn
from app.core.config import settings
from app.core.errors import AppError
from app.llm.types import StreamEvent
from app.models import Agent, AgentVersion, Conversation
from app.modules.conversations.service import (
    _build_chat_request,
    _finalize_turn,
    _live_version,
    _load_history,
    _persist_user_message,
    _resolve_provider,
)
from app.modules.public import schemas
from app.rag.agent_retrieval import retrieve_for_version
from app.tools.service import build_tooling


async def _resolve_agent(session: AsyncSession, public_key: str) -> tuple[Agent, AgentVersion]:
    stmt = select(Agent).where(Agent.public_key == public_key, Agent.deleted_at.is_(None))
    agent = (await session.execute(stmt)).scalar_one_or_none()
    if agent is None:
        raise AppError("public.agent_not_found", "No agent for this key.", 404)
    version = await _live_version(session, agent)
    return agent, version


def _theme(version: AgentVersion) -> schemas.WidgetTheme:
    persona = version.persona or {}
    widget = persona.get("widget") if isinstance(persona.get("widget"), dict) else {}
    widget = widget or {}
    return schemas.WidgetTheme(
        primary_color=widget.get("primaryColor", "#E8590C"),
        position=widget.get("position", "bottom-right"),
        launcher_text=widget.get("launcherText", "Chat with us"),
        branding=widget.get("branding", True),
        mode=widget.get("mode", "dark"),
    )


async def get_config(session: AsyncSession, public_key: str) -> schemas.PublicConfig:
    agent, version = await _resolve_agent(session, public_key)
    persona = version.persona or {}
    name = str(persona.get("displayName") or agent.name)
    return schemas.PublicConfig(
        agent_id=agent.id,
        name=name,
        welcome_message=version.welcome_message or "Hi! How can I help you today?",
        suggested_prompts=list(version.suggested_prompts or []),
        theme=_theme(version),
    )


async def _get_or_create_conversation(
    session: AsyncSession, agent: Agent, data: schemas.PublicChatRequest, visitor_id: str
) -> Conversation:
    if data.conversation_id is not None:
        conv = await session.get(Conversation, data.conversation_id)
        if (
            conv is None
            or conv.agent_id != agent.id
            or conv.organization_id != agent.organization_id
            or conv.channel != "widget"
        ):
            raise AppError("public.conversation_not_found", "Conversation not found.", 404)
        return conv
    meta: dict[str, Any] = {}
    if data.visitor is not None:
        meta["visitor"] = data.visitor.model_dump(exclude_none=True)
    conv = Conversation(
        organization_id=agent.organization_id,
        agent_id=agent.id,
        channel="widget",
        channel_user_id=visitor_id,
        status="active",
        meta=meta,
    )
    session.add(conv)
    await session.flush()
    return conv


async def public_chat_events(
    session: AsyncSession, public_key: str, data: schemas.PublicChatRequest, visitor_id: str
) -> AsyncIterator[StreamEvent]:
    agent, version = await _resolve_agent(session, public_key)
    org_id = agent.organization_id
    conv = await _get_or_create_conversation(session, agent, data, visitor_id)

    history = await _load_history(session, conv.id)
    _persist_user_message(session, conv, data.message)
    await session.flush()

    context_block, citations = await retrieve_for_version(session, org_id, version, data.message)
    messages = build_messages(
        system_prompt=version.system_prompt,
        context_block=context_block,
        memory_summary=conv.memory_summary,
        history=history,
        user_message=data.message,
        window_messages=settings.memory_window_messages,
    )
    provider_name = (version.model_config_json or {}).get("provider", "fake")
    provider = await _resolve_provider(session, org_id, agent, provider_name)
    req = _build_chat_request(version, messages, stream=True)

    specs, executor = await build_tooling(session, org_id, agent, version, conv.id)
    if specs and executor is not None and provider.supports_tools():
        req.tools = specs
    else:
        executor = None

    yield StreamEvent(type="conversation", conversation_id=str(conv.id))
    result = TurnResult()
    t0 = time.perf_counter()
    async for ev in run_turn(
        provider, req, [c.model_dump(mode="json") for c in citations], result,
        executor=executor, max_iters=settings.tool_max_iterations,
    ):
        yield ev
    latency_ms = int((time.perf_counter() - t0) * 1000)
    msg = await _finalize_turn(session, conv, result, latency_ms, data.message)
    yield StreamEvent(type="message", message_id=str(msg.id))


async def public_chat_sse(
    session: AsyncSession, public_key: str, data: schemas.PublicChatRequest, visitor_id: str
) -> AsyncIterator[str]:
    async for ev in public_chat_events(session, public_key, data, visitor_id):
        yield f"data: {ev.model_dump_json()}\n\n"


async def public_chat_once(
    session: AsyncSession, public_key: str, data: schemas.PublicChatRequest, visitor_id: str
) -> dict[str, Any]:
    content = ""
    conversation_id = ""
    citations: list[Any] = []
    async for ev in public_chat_events(session, public_key, data, visitor_id):
        if ev.type == "conversation" and ev.conversation_id:
            conversation_id = ev.conversation_id
        elif ev.type == "token" and ev.delta:
            content += ev.delta
        elif ev.type == "citations" and ev.citations:
            citations = ev.citations
    return {"conversation_id": conversation_id, "content": content.strip(), "citations": citations}


def visitor_id_for(data: schemas.PublicChatRequest) -> str:
    if data.visitor and data.visitor.id:
        return str(data.visitor.id)[:255]
    return f"anon-{uuid.uuid4().hex[:16]}"
