"""Long-term memory: summarize older turns into ``conversation.memory_summary``.

Uses a deliberately small/fast model (``settings.summary_provider``/``summary_model``), never
the agent's own model — so a heavy local model never gets pulled into background summaries.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AppError
from app.core.logging import get_logger
from app.llm.base import ChatProvider, ProviderError
from app.llm.fake import FakeChatProvider
from app.llm.registry import get_chat_provider
from app.llm.types import ChatRequest, Message
from app.models import Conversation

log = get_logger("chat.memory")

_SUMMARY_SYSTEM = (
    "You compress chat history. Given a running summary and newer turns, produce a concise, "
    "factual summary (max ~150 words) capturing the user's goals, key facts, decisions, and "
    "open questions. Write only the summary."
)


async def resolve_summary_provider(session: AsyncSession, org_id: uuid.UUID) -> ChatProvider:
    """Groq (or configured provider) when a key exists; otherwise the fake provider (CLAUDE §7)."""
    try:
        return await get_chat_provider(session, org_id, settings.summary_provider)
    except AppError:
        log.warning("summary_provider_stubbed", provider=settings.summary_provider)
        return FakeChatProvider()


async def summarize(
    session: AsyncSession,
    org_id: uuid.UUID,
    conversation: Conversation,
    older: list[Message],
) -> None:
    """Fold `older` turns into `conversation.memory_summary`. Best-effort; never raises."""
    if not older:
        return
    transcript = "\n".join(f"{m.role}: {m.content or ''}" for m in older if m.content)
    if not transcript.strip():
        return
    prior = conversation.memory_summary or "(none yet)"
    provider = await resolve_summary_provider(session, org_id)
    req = ChatRequest(
        model=settings.summary_model,
        messages=[
            Message(role="system", content=_SUMMARY_SYSTEM),
            Message(role="user", content=f"Running summary:\n{prior}\n\nNewer turns:\n{transcript}"),
        ],
        temperature=0.2,
        max_tokens=300,
    )
    try:
        result = await provider.chat(req)
    except ProviderError as exc:
        log.warning("summarize_failed", conversation_id=str(conversation.id), error=str(exc))
        return
    if result.content.strip():
        conversation.memory_summary = result.content.strip()
