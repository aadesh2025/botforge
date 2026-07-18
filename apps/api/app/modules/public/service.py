"""Public (widget) config + chat runtime — no dashboard auth, keyed by public_key.

Reuses the dashboard chat building blocks (assembly, retrieval, tools, run_turn, persistence);
resolves the agent/org from its ``public_key`` instead of an OrgContext.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat.inbound import InboundTurn
from app.core.errors import AppError
from app.llm.types import StreamEvent
from app.models import Agent, AgentVersion, Conversation
from app.modules.conversations.service import _live_version
from app.modules.public import schemas


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
    conv = await _get_or_create_conversation(session, agent, data, visitor_id)

    yield StreamEvent(type="conversation", conversation_id=str(conv.id))
    turn = InboundTurn(session, agent, version, conv, data.message)
    async for ev in turn.events():
        yield ev


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
