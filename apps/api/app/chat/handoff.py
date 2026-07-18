"""Handoff triggering — pauses the bot and records a handoff (docs/08 §13)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Conversation, Handoff
from app.realtime.hub import hub, inbox_topic
from app.webhooks.dispatch import emit_event

# Keyword triggers checked against the user's message when `features.handoff_enabled`.
HANDOFF_KEYWORDS = (
    "human",
    "real person",
    "real agent",
    "live agent",
    "speak to someone",
    "talk to a person",
    "talk to someone",
    "customer service",
    "representative",
    "agent please",
)


def wants_handoff(text: str) -> bool:
    lowered = (text or "").lower()
    return any(keyword in lowered for keyword in HANDOFF_KEYWORDS)


async def trigger_handoff(
    session: AsyncSession, conversation: Conversation, *, requested_by: str, reason: str | None
) -> Handoff:
    """Pause the bot on this conversation and open a handoff record (idempotent-ish)."""
    conversation.status = "handoff"
    handoff = Handoff(
        organization_id=conversation.organization_id,
        conversation_id=conversation.id,
        requested_by=requested_by,
        reason=reason,
        status="open",
    )
    session.add(handoff)
    await session.flush()
    await hub.publish(
        inbox_topic(conversation.organization_id),
        {
            "type": "handoff.requested",
            "conversation_id": str(conversation.id),
            "handoff_id": str(handoff.id),
            "reason": reason,
            "requested_by": requested_by,
        },
    )
    await emit_event(
        session,
        conversation.organization_id,
        "handoff.requested",
        {"conversation_id": str(conversation.id), "handoff_id": str(handoff.id), "reason": reason},
    )
    return handoff
