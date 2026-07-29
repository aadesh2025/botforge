"""CRM: browse, segment and annotate the *people* behind conversations.

Operates on `CrmContact` (one row per human) rather than `Contact` (one row per handle).
The linked handles come along as `channels`, so an operator can see that the person who
just messaged on Instagram is the same one who emailed last week.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import rbac
from app.core.errors import AppError
from app.crm.extract import normalize_email, normalize_phone
from app.models import Contact, Conversation, CrmContact
from app.modules.contacts import schemas
from app.modules.orgs.deps import OrgContext


def _now_iso() -> str:
    return dt.datetime.now(tz=dt.UTC).isoformat()


def _linked_out(contact: Contact) -> schemas.LinkedChannelOut:
    return schemas.LinkedChannelOut(
        id=contact.id,
        channel=contact.channel,
        external_id=contact.external_id,
        display_name=contact.display_name,
        avatar_url=contact.avatar_url,
    )


def _base_out(
    row: CrmContact,
    *,
    channels: list[Contact],
    last_active: dt.datetime | None,
    conversations: int,
) -> schemas.CrmContactOut:
    return schemas.CrmContactOut(
        id=row.id,
        display_name=row.display_name,
        email=row.email,
        phone=row.phone,
        lead_stage=row.lead_stage,
        order_status=row.order_status,
        labels=list(row.labels),
        created_at=row.created_at,
        updated_at=row.updated_at,
        channels=[_linked_out(c) for c in channels],
        last_active_at=last_active,
        conversation_count=conversations,
    )


async def _get(session: AsyncSession, ctx: OrgContext, contact_id: uuid.UUID) -> CrmContact:
    row = await session.get(CrmContact, contact_id)
    if row is None or row.organization_id != ctx.org.id:
        raise AppError("contacts.not_found", "Contact not found.", 404)
    return row


async def _linked_contacts(
    session: AsyncSession, person_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[Contact]]:
    """Every handle for a page of people, in one query rather than one per row."""
    if not person_ids:
        return {}
    stmt = select(Contact).where(Contact.crm_contact_id.in_(person_ids))
    out: dict[uuid.UUID, list[Contact]] = {}
    for c in (await session.execute(stmt)).scalars().all():
        if c.crm_contact_id is not None:
            out.setdefault(c.crm_contact_id, []).append(c)
    return out


async def _activity(
    session: AsyncSession, contact_ids: list[uuid.UUID]
) -> dict[uuid.UUID, tuple[dt.datetime | None, int]]:
    """Last-active + conversation count, keyed by the *handle* they belong to."""
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


def _apply_filters(
    stmt: Select[tuple[CrmContact]],
    *,
    query: str | None,
    lead_stage: str | None,
    channel: str | None,
    label: str | None,
) -> Select[tuple[CrmContact]]:
    if query:
        # Name, email or phone on the person — or the raw platform id of any linked handle,
        # since an operator searching "15551234" means the number they see in the inbox.
        like = f"%{query.strip()}%"
        handle_match = select(Contact.crm_contact_id).where(Contact.external_id.ilike(like))
        stmt = stmt.where(
            or_(
                CrmContact.display_name.ilike(like),
                CrmContact.email.ilike(like),
                CrmContact.phone.ilike(like),
                CrmContact.id.in_(handle_match),
            )
        )
    if lead_stage:
        stmt = stmt.where(CrmContact.lead_stage == lead_stage)
    if channel:
        # "People reachable on X" — expressed through their handles.
        on_channel = select(Contact.crm_contact_id).where(Contact.channel == channel)
        stmt = stmt.where(CrmContact.id.in_(on_channel))
    if label:
        stmt = stmt.where(CrmContact.labels.contains([label]))
    return stmt


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
        select(CrmContact).where(CrmContact.organization_id == ctx.org.id),
        query=query,
        lead_stage=lead_stage,
        channel=channel,
        label=label,
    )
    total = int(
        (
            await session.execute(select(func.count()).select_from(filtered.order_by(None).subquery()))
        ).scalar_one()
    )
    rows = (
        (
            await session.execute(
                filtered.order_by(CrmContact.updated_at.desc()).limit(limit).offset(offset)
            )
        )
        .scalars()
        .all()
    )

    linked = await _linked_contacts(session, [r.id for r in rows])
    handle_ids = [c.id for group in linked.values() for c in group]
    activity = await _activity(session, handle_ids)

    items: list[schemas.CrmContactOut] = []
    for row in rows:
        handles = linked.get(row.id, [])
        stats = [activity.get(c.id, (None, 0)) for c in handles]
        last_active = max((s[0] for s in stats if s[0] is not None), default=None)
        items.append(
            _base_out(
                row,
                channels=handles,
                last_active=last_active,
                conversations=sum(s[1] for s in stats),
            )
        )
    return schemas.ContactListOut(items=items, total=total, limit=limit, offset=offset)


async def get_contact(
    session: AsyncSession, ctx: OrgContext, contact_id: uuid.UUID
) -> schemas.ContactDetail:
    rbac.require_permission(ctx.role, rbac.READ)
    row = await _get(session, ctx, contact_id)
    handles = (
        (await session.execute(select(Contact).where(Contact.crm_contact_id == row.id)))
        .scalars()
        .all()
    )
    convs = []
    if handles:
        convs = list(
            (
                await session.execute(
                    select(Conversation)
                    .where(Conversation.contact_id.in_([c.id for c in handles]))
                    .order_by(
                        func.coalesce(Conversation.last_message_at, Conversation.created_at).desc()
                    )
                )
            )
            .scalars()
            .all()
        )
    last_active = max((c.last_message_at or c.created_at for c in convs), default=None)
    base = _base_out(row, channels=list(handles), last_active=last_active, conversations=len(convs))
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


async def create_contact(
    session: AsyncSession, ctx: OrgContext, data: schemas.CreateContactRequest
) -> schemas.ContactDetail:
    """Add a person by hand — the one path into the CRM that isn't a chat message.

    A `manual` handle is created alongside so the origin is visible in the channels row,
    and so the person is reachable by the same `(org, channel, external_id)` lookups as
    everyone else.
    """
    rbac.require_permission(ctx.role, rbac.INBOX_HANDLE)
    person = CrmContact(
        organization_id=ctx.org.id,
        display_name=data.display_name.strip(),
        email=normalize_email(data.email),
        phone=normalize_phone(data.phone),
        lead_stage=data.lead_stage,
        order_status=data.order_status or None,
    )
    session.add(person)
    await session.flush()

    session.add(
        Contact(
            organization_id=ctx.org.id,
            channel="manual",
            external_id=f"manual-{uuid.uuid4()}",
            display_name=person.display_name,
            crm_contact_id=person.id,
        )
    )
    await session.flush()
    return await get_contact(session, ctx, person.id)


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
        row.display_name = data.display_name
    # Normalised on write so a hand-typed detail still matches an auto-captured one later.
    if "email" in fields:
        row.email = normalize_email(data.email)
    if "phone" in fields:
        row.phone = normalize_phone(data.phone)
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
