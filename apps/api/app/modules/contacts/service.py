"""Contacts CRM: list/segment/annotate the people behind conversations."""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import rbac
from app.core.errors import AppError
from app.models import Contact, Conversation
from app.modules.contacts import schemas
from app.modules.orgs.deps import OrgContext


def _now_iso() -> str:
    return dt.datetime.now(tz=dt.UTC).isoformat()


def _base_out(row: Contact, *, last_active: dt.datetime | None, conversations: int) -> schemas.ContactOut:
    return schemas.ContactOut(
        id=row.id,
        channel=row.channel,
        external_id=row.external_id,
        display_name=row.display_name,
        avatar_url=row.avatar_url,
        lead_stage=row.lead_stage,
        order_status=row.order_status,
        labels=list(row.labels),
        extra=row.extra,
        created_at=row.created_at,
        updated_at=row.updated_at,
        last_active_at=last_active,
        conversation_count=conversations,
    )


async def _get(session: AsyncSession, ctx: OrgContext, contact_id: uuid.UUID) -> Contact:
    row = await session.get(Contact, contact_id)
    if row is None or row.organization_id != ctx.org.id:
        raise AppError("contacts.not_found", "Contact not found.", 404)
    return row


def _apply_filters(
    stmt: Select[tuple[Contact]],
    *,
    query: str | None,
    lead_stage: str | None,
    channel: str | None,
    label: str | None,
) -> Select[tuple[Contact]]:
    if query:
        # Name *or* platform id: an operator searching "15551234" means the phone number.
        like = f"%{query.strip()}%"
        stmt = stmt.where(Contact.display_name.ilike(like) | Contact.external_id.ilike(like))
    if lead_stage:
        stmt = stmt.where(Contact.lead_stage == lead_stage)
    if channel:
        stmt = stmt.where(Contact.channel == channel)
    if label:
        # `@>` containment, which is what the GIN index on `labels` serves.
        stmt = stmt.where(Contact.labels.contains([label]))
    return stmt


async def _activity(
    session: AsyncSession, contact_ids: list[uuid.UUID]
) -> dict[uuid.UUID, tuple[dt.datetime | None, int]]:
    """Last-active + conversation count for a page of contacts, in one query."""
    if not contact_ids:
        return {}
    stmt = (
        select(
            Conversation.contact_id,
            func.max(func.coalesce(Conversation.last_message_at, Conversation.created_at)),
            func.count(),
        )
        .where(Conversation.contact_id.in_(contact_ids))
        .group_by(Conversation.contact_id)
    )
    return {r[0]: (r[1], int(r[2])) for r in (await session.execute(stmt)).all()}


async def list_contacts(
    session: AsyncSession,
    ctx: OrgContext,
    *,
    query: str | None = None,
    lead_stage: str | None = None,
    channel: str | None = None,
    label: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> schemas.ContactListOut:
    rbac.require_permission(ctx.role, rbac.READ)

    filtered = _apply_filters(
        select(Contact).where(Contact.organization_id == ctx.org.id),
        query=query,
        lead_stage=lead_stage,
        channel=channel,
        label=label,
    )
    total = int(
        (
            await session.execute(
                select(func.count()).select_from(filtered.order_by(None).subquery())
            )
        ).scalar_one()
    )
    rows = (
        (await session.execute(filtered.order_by(Contact.updated_at.desc()).limit(limit).offset(offset)))
        .scalars()
        .all()
    )
    activity = await _activity(session, [r.id for r in rows])
    items = [
        _base_out(r, last_active=activity.get(r.id, (None, 0))[0], conversations=activity.get(r.id, (None, 0))[1])
        for r in rows
    ]
    return schemas.ContactListOut(items=items, total=total, limit=limit, offset=offset)


async def get_contact(session: AsyncSession, ctx: OrgContext, contact_id: uuid.UUID) -> schemas.ContactDetail:
    rbac.require_permission(ctx.role, rbac.READ)
    row = await _get(session, ctx, contact_id)
    convs = (
        (
            await session.execute(
                select(Conversation)
                .where(Conversation.contact_id == row.id)
                .order_by(func.coalesce(Conversation.last_message_at, Conversation.created_at).desc())
            )
        )
        .scalars()
        .all()
    )
    last_active = max(
        (c.last_message_at or c.created_at for c in convs), default=None
    )
    base = _base_out(row, last_active=last_active, conversations=len(convs))
    return schemas.ContactDetail(
        **base.model_dump(),
        notes=[schemas.ContactNote(**n) for n in row.notes],
        conversations=[
            schemas.ContactConversationOut(
                id=c.id,
                agent_id=c.agent_id,
                channel=c.channel,
                status=c.status,
                title=c.title,
                last_message_at=c.last_message_at,
                created_at=c.created_at,
            )
            for c in convs
        ],
    )


async def update_contact(
    session: AsyncSession, ctx: OrgContext, contact_id: uuid.UUID, data: schemas.UpdateContactRequest
) -> schemas.ContactDetail:
    rbac.require_permission(ctx.role, rbac.INBOX_HANDLE)
    row = await _get(session, ctx, contact_id)
    fields = data.model_dump(exclude_unset=True)
    if "lead_stage" in fields:
        row.lead_stage = data.lead_stage
    if "order_status" in fields:
        row.order_status = data.order_status or None
    if "display_name" in fields and data.display_name:
        # Operator-set names win: a later platform payload only fills blanks.
        row.display_name = data.display_name
    await session.flush()
    return await get_contact(session, ctx, contact_id)


async def set_labels(
    session: AsyncSession, ctx: OrgContext, contact_id: uuid.UUID, labels: list[str]
) -> schemas.ContactDetail:
    rbac.require_permission(ctx.role, rbac.INBOX_HANDLE)
    row = await _get(session, ctx, contact_id)
    row.labels = labels
    await session.flush()
    return await get_contact(session, ctx, contact_id)


async def add_note(
    session: AsyncSession, ctx: OrgContext, contact_id: uuid.UUID, text: str
) -> schemas.ContactDetail:
    rbac.require_permission(ctx.role, rbac.INBOX_HANDLE)
    row = await _get(session, ctx, contact_id)
    # Same {"by","text","at"} shape as Handoff.notes so both timelines render identically.
    row.notes = [*row.notes, {"by": str(ctx.user.id), "text": text, "at": _now_iso()}]
    await session.flush()
    return await get_contact(session, ctx, contact_id)
