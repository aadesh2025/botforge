"""Inbox: handoff queue, operator actions, and operator-reply delivery."""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels import get_channel
from app.core import rbac
from app.core.errors import AppError
from app.core.logging import get_logger
from app.models import Channel, Contact, Conversation, Handoff, Message
from app.modules.conversations.schemas import MessageOut
from app.modules.conversations.service import _message_out
from app.modules.inbox import schemas
from app.modules.orgs.deps import OrgContext
from app.realtime.hub import conv_topic, hub, inbox_topic
from app.webhooks.dispatch import emit_event

log = get_logger("inbox")

_CHANNEL_TYPES = ("telegram", "whatsapp", "instagram", "facebook", "slack", "discord")


def _now() -> dt.datetime:
    return dt.datetime.now(tz=dt.UTC)


async def _get_conversation(session: AsyncSession, ctx: OrgContext, cid: uuid.UUID) -> Conversation:
    conv = await session.get(Conversation, cid)
    if conv is None or conv.organization_id != ctx.org.id:
        raise AppError("inbox.not_found", "Conversation not found.", 404)
    return conv


async def _latest_handoff(session: AsyncSession, conversation_id: uuid.UUID) -> Handoff | None:
    stmt = (
        select(Handoff)
        .where(Handoff.conversation_id == conversation_id)
        .order_by(Handoff.created_at.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


def _handoff_out(handoff: Handoff | None) -> schemas.HandoffOut | None:
    if handoff is None:
        return None
    return schemas.HandoffOut(
        id=handoff.id,
        status=handoff.status,
        requested_by=handoff.requested_by,
        reason=handoff.reason,
        assigned_to=handoff.assigned_to,
        notes=handoff.notes,
        tags=handoff.tags,
        created_at=handoff.created_at,
        resolved_at=handoff.resolved_at,
    )


async def _message_count(session: AsyncSession, conversation_id: uuid.UUID) -> int:
    stmt = select(func.count()).select_from(Message).where(Message.conversation_id == conversation_id)
    return int((await session.execute(stmt)).scalar_one())


def _contact_out(contact: Contact | None) -> schemas.ContactOut | None:
    if contact is None:
        return None
    return schemas.ContactOut(
        id=contact.id, display_name=contact.display_name, avatar_url=contact.avatar_url
    )


async def _contacts_by_id(
    session: AsyncSession, convs: Sequence[Conversation]
) -> dict[uuid.UUID, Contact]:
    """One query for the whole page's contacts, rather than one per row."""
    ids = {c.contact_id for c in convs if c.contact_id is not None}
    if not ids:
        return {}
    stmt = select(Contact).where(Contact.id.in_(ids))
    return {c.id: c for c in (await session.execute(stmt)).scalars().all()}


async def _item_out(
    session: AsyncSession, conv: Conversation, contact: Contact | None = None
) -> schemas.InboxItemOut:
    if contact is None and conv.contact_id is not None:
        contact = await session.get(Contact, conv.contact_id)
    return schemas.InboxItemOut(
        id=conv.id,
        agent_id=conv.agent_id,
        channel=conv.channel,
        status=conv.status,
        title=conv.title,
        channel_user_id=conv.channel_user_id,
        message_count=await _message_count(session, conv.id),
        last_message_at=conv.last_message_at,
        created_at=conv.created_at,
        handoff=_handoff_out(await _latest_handoff(session, conv.id)),
        contact=_contact_out(contact),
    )


# ── Queue + detail ───────────────────────────────────────────────────────────────
async def list_conversations(
    session: AsyncSession,
    ctx: OrgContext,
    status_filter: str | None,
    channel_filter: str | None = None,
) -> list[schemas.InboxItemOut]:
    rbac.require_permission(ctx.role, rbac.INBOX_HANDLE)
    # Conversations that have at least one handoff record form the inbox queue.
    handoff_ids = select(Handoff.conversation_id).where(Handoff.organization_id == ctx.org.id)
    stmt = (
        select(Conversation)
        .where(Conversation.organization_id == ctx.org.id, Conversation.id.in_(handoff_ids))
        .order_by(func.coalesce(Conversation.last_message_at, Conversation.created_at).desc())
    )
    if status_filter:
        stmt = stmt.where(Conversation.status == status_filter)
    if channel_filter:
        # Server-side so the channel tabs page independently instead of slicing one
        # client-held list.
        stmt = stmt.where(Conversation.channel == channel_filter)
    convs = (await session.execute(stmt)).scalars().all()
    contacts = await _contacts_by_id(session, convs)
    return [await _item_out(session, c, contacts.get(c.contact_id) if c.contact_id else None) for c in convs]


async def get_detail(session: AsyncSession, ctx: OrgContext, cid: uuid.UUID) -> schemas.InboxDetail:
    rbac.require_permission(ctx.role, rbac.INBOX_HANDLE)
    conv = await _get_conversation(session, ctx, cid)
    base = await _item_out(session, conv)
    stmt = select(Message).where(Message.conversation_id == cid).order_by(Message.created_at.asc())
    msgs = list((await session.execute(stmt)).scalars().all())
    return schemas.InboxDetail(**base.model_dump(), messages=[_message_out(m) for m in msgs])


# ── Operator actions ─────────────────────────────────────────────────────────────
async def _require_open_handoff(session: AsyncSession, conv: Conversation) -> Handoff:
    handoff = await _latest_handoff(session, conv.id)
    if handoff is None:
        raise AppError("inbox.no_handoff", "This conversation has no handoff.", 400)
    return handoff


async def _publish_inbox(session: AsyncSession, ctx: OrgContext, conv: Conversation, event_type: str) -> None:
    await hub.publish(
        inbox_topic(ctx.org.id),
        {"type": event_type, "conversation_id": str(conv.id), "status": conv.status},
    )


async def takeover(session: AsyncSession, ctx: OrgContext, cid: uuid.UUID) -> schemas.InboxItemOut:
    rbac.require_permission(ctx.role, rbac.INBOX_HANDLE)
    conv = await _get_conversation(session, ctx, cid)
    handoff = await _require_open_handoff(session, conv)
    handoff.status = "assigned"
    handoff.assigned_to = ctx.user.id
    conv.assigned_to = ctx.user.id
    conv.status = "handoff"
    await session.flush()
    await _publish_inbox(session, ctx, conv, "handoff.assigned")
    return await _item_out(session, conv)


async def handback(session: AsyncSession, ctx: OrgContext, cid: uuid.UUID) -> schemas.InboxItemOut:
    rbac.require_permission(ctx.role, rbac.INBOX_HANDLE)
    conv = await _get_conversation(session, ctx, cid)
    handoff = await _require_open_handoff(session, conv)
    handoff.status = "resolved"
    handoff.resolved_at = _now()
    conv.status = "active"  # bot resumes
    conv.assigned_to = None
    await session.flush()
    await _publish_inbox(session, ctx, conv, "handoff.resolved")
    await emit_event(session, ctx.org.id, "handoff.resolved", {"conversation_id": str(conv.id)})
    await hub.publish(conv_topic(conv.id), {"type": "handback", "content": "You're back with the assistant."})
    return await _item_out(session, conv)


async def close(session: AsyncSession, ctx: OrgContext, cid: uuid.UUID) -> schemas.InboxItemOut:
    rbac.require_permission(ctx.role, rbac.INBOX_HANDLE)
    conv = await _get_conversation(session, ctx, cid)
    handoff = await _latest_handoff(session, conv.id)
    if handoff is not None and handoff.status != "resolved":
        handoff.status = "resolved"
        handoff.resolved_at = _now()
    conv.status = "closed"
    await session.flush()
    await _publish_inbox(session, ctx, conv, "conversation.closed")
    await emit_event(session, ctx.org.id, "conversation.closed", {"conversation_id": str(conv.id)})
    if handoff is not None:
        await emit_event(session, ctx.org.id, "handoff.resolved", {"conversation_id": str(conv.id)})
    return await _item_out(session, conv)


async def assign(session: AsyncSession, ctx: OrgContext, cid: uuid.UUID, user_id: uuid.UUID) -> schemas.InboxItemOut:
    rbac.require_permission(ctx.role, rbac.INBOX_HANDLE)
    conv = await _get_conversation(session, ctx, cid)
    handoff = await _require_open_handoff(session, conv)
    handoff.assigned_to = user_id
    handoff.status = "assigned"
    conv.assigned_to = user_id
    await session.flush()
    await _publish_inbox(session, ctx, conv, "handoff.assigned")
    return await _item_out(session, conv)


async def add_note(session: AsyncSession, ctx: OrgContext, cid: uuid.UUID, text: str) -> schemas.HandoffOut:
    rbac.require_permission(ctx.role, rbac.INBOX_HANDLE)
    conv = await _get_conversation(session, ctx, cid)
    handoff = await _require_open_handoff(session, conv)
    handoff.notes = [*handoff.notes, {"by": str(ctx.user.id), "text": text, "at": _now().isoformat()}]
    await session.flush()
    return _handoff_out(handoff)  # type: ignore[return-value]


async def set_tags(session: AsyncSession, ctx: OrgContext, cid: uuid.UUID, tags: list[str]) -> schemas.HandoffOut:
    rbac.require_permission(ctx.role, rbac.INBOX_HANDLE)
    conv = await _get_conversation(session, ctx, cid)
    handoff = await _require_open_handoff(session, conv)
    handoff.tags = tags
    await session.flush()
    return _handoff_out(handoff)  # type: ignore[return-value]


async def operator_reply(session: AsyncSession, ctx: OrgContext, cid: uuid.UUID, text: str) -> MessageOut:
    rbac.require_permission(ctx.role, rbac.INBOX_HANDLE)
    conv = await _get_conversation(session, ctx, cid)
    msg = Message(
        conversation_id=conv.id,
        organization_id=conv.organization_id,
        role="assistant",
        content=text,
        provider="operator",
    )
    session.add(msg)
    conv.last_message_at = _now()
    await session.flush()

    await _deliver_to_user(session, conv, text)
    await hub.publish(
        conv_topic(conv.id),
        {"type": "operator_message", "content": text, "message_id": str(msg.id)},
    )
    await _publish_inbox(session, ctx, conv, "message.created")
    return _message_out(msg)


async def _deliver_to_user(session: AsyncSession, conv: Conversation, text: str) -> None:
    """Push the operator's reply to the end user's channel (widget receives it via the hub)."""
    if conv.channel not in _CHANNEL_TYPES or not conv.channel_user_id:
        return
    stmt = (
        select(Channel)
        .where(
            Channel.organization_id == conv.organization_id,
            Channel.agent_id == conv.agent_id,
            Channel.type == conv.channel,
        )
        .limit(1)
    )
    channel = (await session.execute(stmt)).scalar_one_or_none()
    adapter = get_channel(conv.channel)
    if channel is None or adapter is None:
        return
    try:
        await adapter.send(channel, conv.channel_user_id, text)
    except Exception as exc:  # delivery failure shouldn't fail the operator's action
        log.warning("operator_reply_delivery_failed", conversation=str(conv.id), error=str(exc))


# ── Realtime ───────────────────────────────────────────────────────────────────────
async def inbox_stream(org_id: uuid.UUID) -> Any:
    """Subscribe to this org's inbox topic; yields events until cancelled."""
    return hub.subscribe(inbox_topic(org_id))
