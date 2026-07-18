"""Conversation persistence, the dashboard chat runtime, and memory."""

from __future__ import annotations

import datetime as dt
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat import memory
from app.chat.assembly import build_messages
from app.chat.runtime import ToolExecutor, TurnResult, run_turn
from app.core import rbac
from app.core.config import settings
from app.core.errors import AppError
from app.core.logging import get_logger
from app.llm.base import ChatProvider
from app.llm.fake import FakeChatProvider
from app.llm.registry import get_chat_provider
from app.llm.types import ChatRequest, StreamEvent
from app.llm.types import Message as LLMMessage
from app.models import Agent, AgentVersion, Conversation, Message
from app.modules.conversations import schemas
from app.modules.orgs.deps import OrgContext
from app.rag.agent_retrieval import retrieve_for_version
from app.tools.service import build_tooling
from app.webhooks.dispatch import emit_event

log = get_logger("conversations")

_HISTORY_FETCH = 100  # most-recent messages loaded before trimming to the prompt window


def _now() -> dt.datetime:
    return dt.datetime.now(tz=dt.UTC)


# ── Lookups ─────────────────────────────────────────────────────────────────────
async def _get_agent(session: AsyncSession, ctx: OrgContext, agent_id: uuid.UUID) -> Agent:
    agent = await session.get(Agent, agent_id)
    if agent is None or agent.organization_id != ctx.org.id or agent.deleted_at is not None:
        raise AppError("agents.not_found", "Agent not found.", 404)
    return agent


async def _live_version(session: AsyncSession, agent: Agent) -> AgentVersion:
    """The version that answers: the published current version, else the latest draft."""
    if agent.current_version_id is not None:
        version = await session.get(AgentVersion, agent.current_version_id)
        if version is not None:
            return version
    stmt = (
        select(AgentVersion)
        .where(AgentVersion.agent_id == agent.id)
        .order_by(AgentVersion.version.desc())
        .limit(1)
    )
    version = (await session.execute(stmt)).scalar_one_or_none()
    if version is None:
        raise AppError("agents.no_version", "Agent has no versions.", 500)
    return version


async def _get_conversation(session: AsyncSession, ctx: OrgContext, cid: uuid.UUID) -> Conversation:
    conv = await session.get(Conversation, cid)
    if conv is None or conv.organization_id != ctx.org.id:
        raise AppError("conversations.not_found", "Conversation not found.", 404)
    return conv


async def _get_or_create_conversation(
    session: AsyncSession, ctx: OrgContext, agent: Agent, conversation_id: uuid.UUID | None
) -> Conversation:
    if conversation_id is not None:
        conv = await _get_conversation(session, ctx, conversation_id)
        if conv.agent_id != agent.id:
            raise AppError("conversations.agent_mismatch", "Conversation belongs to another agent.", 400)
        return conv
    conv = Conversation(
        organization_id=ctx.org.id,
        agent_id=agent.id,
        channel="dashboard",
        status="active",
    )
    session.add(conv)
    await session.flush()
    await emit_event(
        session, ctx.org.id, "conversation.created", {"conversation_id": str(conv.id), "channel": "dashboard"}
    )
    return conv


async def _load_history(session: AsyncSession, conversation_id: uuid.UUID) -> list[LLMMessage]:
    stmt = (
        select(Message)
        .where(
            Message.conversation_id == conversation_id,
            Message.role.in_(("user", "assistant", "tool")),
            Message.content.is_not(None),
        )
        .order_by(Message.created_at.desc())
        .limit(_HISTORY_FETCH)
    )
    rows = list((await session.execute(stmt)).scalars().all())
    rows.reverse()
    return [LLMMessage(role=m.role, content=m.content) for m in rows]


def _build_chat_request(version: AgentVersion, messages: list[LLMMessage], stream: bool) -> ChatRequest:
    mc = version.model_config_json or {}
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


async def _resolve_provider(session: AsyncSession, org_id: uuid.UUID, agent: Agent, provider: str) -> ChatProvider:
    try:
        return await get_chat_provider(session, org_id, provider, agent_id=agent.id)
    except AppError:
        log.warning("chat_stub_provider", provider=provider, agent_id=str(agent.id))
        return FakeChatProvider()


# ── Persistence ─────────────────────────────────────────────────────────────────
def _persist_user_message(session: AsyncSession, conv: Conversation, text: str) -> Message:
    msg = Message(conversation_id=conv.id, organization_id=conv.organization_id, role="user", content=text)
    session.add(msg)
    return msg


def _persist_assistant_message(
    session: AsyncSession, conv: Conversation, result: TurnResult, latency_ms: int
) -> Message:
    msg = Message(
        conversation_id=conv.id,
        organization_id=conv.organization_id,
        role="assistant",
        content=(result.content or "").strip() or None,
        citations=result.citations,
        provider=result.provider or None,
        model=result.model or None,
        tokens_prompt=result.prompt_tokens,
        tokens_completion=result.completion_tokens,
        cost_micros=result.cost_micros,
        latency_ms=latency_ms,
        error=result.error,
    )
    session.add(msg)
    return msg


async def _message_count(session: AsyncSession, conversation_id: uuid.UUID) -> int:
    stmt = select(func.count()).select_from(Message).where(Message.conversation_id == conversation_id)
    return int((await session.execute(stmt)).scalar_one())


async def _maybe_summarize(session: AsyncSession, org_id: uuid.UUID, conv: Conversation) -> None:
    """Fold newly aged-out messages into `conv.memory_summary` when over the threshold."""
    total = await _message_count(session, conv.id)
    if total <= settings.memory_summary_threshold:
        return
    window = settings.memory_window_messages
    cut = total - window  # messages older than the recent window
    summarized_upto = int(conv.meta.get("summarized_upto", 0))
    if cut - summarized_upto < window:
        return  # not enough new aged-out messages to bother
    stmt = (
        select(Message)
        .where(Message.conversation_id == conv.id, Message.role.in_(("user", "assistant")))
        .order_by(Message.created_at.asc())
        .offset(summarized_upto)
        .limit(cut - summarized_upto)
    )
    older = list((await session.execute(stmt)).scalars().all())
    llm_older = [LLMMessage(role=m.role, content=m.content) for m in older if m.content]
    await memory.summarize(session, org_id, conv, llm_older)
    conv.meta = {**conv.meta, "summarized_upto": cut}


# ── Chat runtime ─────────────────────────────────────────────────────────────────
async def _prepare_turn(
    session: AsyncSession, ctx: OrgContext, agent_id: uuid.UUID, data: schemas.ChatRequest, stream: bool
) -> tuple[Conversation, ChatProvider, ChatRequest, list[dict[str, Any]], ToolExecutor | None]:
    agent = await _get_agent(session, ctx, agent_id)
    version = await _live_version(session, agent)
    conv = await _get_or_create_conversation(session, ctx, agent, data.conversation_id)

    history = await _load_history(session, conv.id)
    _persist_user_message(session, conv, data.message)
    await session.flush()

    context_block, citations = await retrieve_for_version(session, ctx.org.id, version, data.message)
    messages = build_messages(
        system_prompt=version.system_prompt,
        context_block=context_block,
        memory_summary=conv.memory_summary,
        history=history,
        user_message=data.message,
        window_messages=settings.memory_window_messages,
    )
    provider_name = (version.model_config_json or {}).get("provider", "fake")
    provider = await _resolve_provider(session, ctx.org.id, agent, provider_name)
    req = _build_chat_request(version, messages, stream=stream)

    # Tool calling: attach the agent's enabled tools when the provider supports them.
    specs, executor = await build_tooling(session, ctx.org.id, agent, version, conv.id)
    if specs and executor is not None and provider.supports_tools():
        req.tools = specs
    else:
        executor = None
    return conv, provider, req, [c.model_dump(mode="json") for c in citations], executor


async def _finalize_turn(
    session: AsyncSession, conv: Conversation, result: TurnResult, latency_ms: int, first_text: str
) -> Message:
    """Persist the assistant message, bump the conversation, and maybe summarize. Reused by public chat."""
    msg = _persist_assistant_message(session, conv, result, latency_ms)
    conv.last_message_at = _now()
    if not conv.title:
        conv.title = first_text[:80]
    await session.flush()
    await _maybe_summarize(session, conv.organization_id, conv)
    await emit_event(
        session,
        conv.organization_id,
        "message.created",
        {"conversation_id": str(conv.id), "message_id": str(msg.id), "role": "assistant"},
    )
    return msg


async def chat_events(
    session: AsyncSession, ctx: OrgContext, agent_id: uuid.UUID, data: schemas.ChatRequest
) -> AsyncIterator[StreamEvent]:
    """Yield StreamEvents for one turn, persisting user + assistant messages. SSE/WS format upstream."""
    rbac.require_permission(ctx.role, rbac.READ)
    conv, provider, req, citations, executor = await _prepare_turn(session, ctx, agent_id, data, stream=True)

    # Tell the client which conversation this is (esp. for a freshly created one).
    yield StreamEvent(type="conversation", conversation_id=str(conv.id))

    result = TurnResult()
    t0 = time.perf_counter()
    async for ev in run_turn(
        provider, req, citations, result, executor=executor, max_iters=settings.tool_max_iterations
    ):
        yield ev
    latency_ms = int((time.perf_counter() - t0) * 1000)

    msg = await _finalize_turn(session, conv, result, latency_ms, data.message)
    yield StreamEvent(type="message", message_id=str(msg.id))


async def chat_sse(
    session: AsyncSession, ctx: OrgContext, agent_id: uuid.UUID, data: schemas.ChatRequest
) -> AsyncIterator[str]:
    async for ev in chat_events(session, ctx, agent_id, data):
        yield f"data: {ev.model_dump_json()}\n\n"


async def chat_once(
    session: AsyncSession, ctx: OrgContext, agent_id: uuid.UUID, data: schemas.ChatRequest
) -> dict[str, Any]:
    rbac.require_permission(ctx.role, rbac.READ)
    conv, provider, req, citations, executor = await _prepare_turn(session, ctx, agent_id, data, stream=False)

    result = TurnResult()
    t0 = time.perf_counter()
    async for _ev in run_turn(
        provider, req, citations, result, executor=executor, max_iters=settings.tool_max_iterations
    ):
        pass
    latency_ms = int((time.perf_counter() - t0) * 1000)

    msg = await _finalize_turn(session, conv, result, latency_ms, data.message)
    return {
        "conversation_id": str(conv.id),
        "message_id": str(msg.id),
        "content": (result.content or "").strip(),
        "citations": result.citations,
        "tool_runs": result.tool_runs,
        "provider": result.provider,
        "model": result.model,
        "usage": {"prompt_tokens": result.prompt_tokens, "completion_tokens": result.completion_tokens},
        "cost_micros": result.cost_micros,
        "error": result.error,
    }


# ── Conversation CRUD ─────────────────────────────────────────────────────────────
def _message_out(m: Message) -> schemas.MessageOut:
    return schemas.MessageOut(
        id=m.id,
        role=m.role,
        content=m.content,
        tool_calls=m.tool_calls,
        tool_call_id=m.tool_call_id,
        citations=m.citations,
        provider=m.provider,
        model=m.model,
        tokens_prompt=m.tokens_prompt,
        tokens_completion=m.tokens_completion,
        cost_micros=m.cost_micros,
        latency_ms=m.latency_ms,
        error=m.error,
        created_at=m.created_at,
    )


def _conversation_out(conv: Conversation, count: int) -> schemas.ConversationOut:
    return schemas.ConversationOut(
        id=conv.id,
        agent_id=conv.agent_id,
        channel=conv.channel,
        status=conv.status,
        title=conv.title,
        message_count=count,
        last_message_at=conv.last_message_at,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
    )


async def list_conversations(
    session: AsyncSession, ctx: OrgContext, agent_id: uuid.UUID | None
) -> list[schemas.ConversationOut]:
    rbac.require_permission(ctx.role, rbac.READ)
    count_sub = (
        select(Message.conversation_id, func.count().label("n"))
        .group_by(Message.conversation_id)
        .subquery()
    )
    stmt = (
        select(Conversation, func.coalesce(count_sub.c.n, 0))
        .outerjoin(count_sub, count_sub.c.conversation_id == Conversation.id)
        .where(Conversation.organization_id == ctx.org.id)
        .order_by(func.coalesce(Conversation.last_message_at, Conversation.created_at).desc())
    )
    if agent_id is not None:
        stmt = stmt.where(Conversation.agent_id == agent_id)
    rows = (await session.execute(stmt)).all()
    return [_conversation_out(conv, int(n)) for conv, n in rows]


async def get_conversation(session: AsyncSession, ctx: OrgContext, cid: uuid.UUID) -> schemas.ConversationDetail:
    rbac.require_permission(ctx.role, rbac.READ)
    conv = await _get_conversation(session, ctx, cid)
    stmt = select(Message).where(Message.conversation_id == cid).order_by(Message.created_at.asc())
    msgs = list((await session.execute(stmt)).scalars().all())
    base = _conversation_out(conv, len(msgs))
    return schemas.ConversationDetail(
        **base.model_dump(),
        memory_summary=conv.memory_summary,
        messages=[_message_out(m) for m in msgs],
    )


async def get_messages(session: AsyncSession, ctx: OrgContext, cid: uuid.UUID) -> list[schemas.MessageOut]:
    rbac.require_permission(ctx.role, rbac.READ)
    await _get_conversation(session, ctx, cid)
    stmt = select(Message).where(Message.conversation_id == cid).order_by(Message.created_at.asc())
    return [_message_out(m) for m in (await session.execute(stmt)).scalars().all()]


async def update_conversation(
    session: AsyncSession, ctx: OrgContext, cid: uuid.UUID, data: schemas.UpdateConversationRequest
) -> schemas.ConversationOut:
    rbac.require_permission(ctx.role, rbac.AGENTS_WRITE)
    conv = await _get_conversation(session, ctx, cid)
    if data.title is not None:
        conv.title = data.title
    if data.status is not None:
        conv.status = data.status
    return _conversation_out(conv, await _message_count(session, cid))


async def delete_conversation(session: AsyncSession, ctx: OrgContext, cid: uuid.UUID) -> None:
    rbac.require_permission(ctx.role, rbac.AGENTS_WRITE)
    conv = await _get_conversation(session, ctx, cid)
    await session.delete(conv)
