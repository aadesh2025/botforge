"""Upsert a Contact from whatever identity an inbound message carried.

Every channel funnels through here so the inbox has one rule for "who is this":
first sight creates the row, later messages refresh the name/avatar when the platform
sends something fresher. A blank field never overwrites a known one — platforms drop
profile data from some payload shapes, and losing a name we already had would look
like a bug to the operator.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.base import BaseChannel, ContactProfile
from app.core.logging import get_logger
from app.models import Channel, Contact

log = get_logger("contacts")


async def upsert_contact(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    channel: str,
    external_id: str,
    profile: ContactProfile | None = None,
) -> Contact:
    """Create or refresh the contact for (org, channel, external_id)."""
    profile = profile or ContactProfile()
    external_id = external_id[:255]
    display_name = (profile.display_name or None) and profile.display_name[:255]
    avatar_url = (profile.avatar_url or None) and profile.avatar_url[:1024]
    extra = profile.extra or {}

    base = pg_insert(Contact).values(
        organization_id=organization_id,
        channel=channel,
        external_id=external_id,
        display_name=display_name,
        avatar_url=avatar_url,
        extra=extra,
    )
    stmt = base.on_conflict_do_update(
        index_elements=["organization_id", "channel", "external_id"],
        set_={
            # COALESCE(new, old): fresher data wins, absent data leaves the row alone.
            "display_name": func.coalesce(base.excluded.display_name, Contact.display_name),
            "avatar_url": func.coalesce(base.excluded.avatar_url, Contact.avatar_url),
            # JSONB concat: merge new keys over old ones rather than replacing the blob.
            "extra": Contact.extra.op("||")(base.excluded.extra),
            "updated_at": func.now(),
        },
    ).returning(Contact)
    # populate_existing: the row may already sit in the identity map from an earlier
    # message in this request — take the freshly-returned values, not the stale ones.
    result = await session.execute(stmt, execution_options={"populate_existing": True})
    return result.scalar_one()


async def resolve_contact(
    session: AsyncSession,
    channel: Channel,
    adapter: BaseChannel,
    external_id: str,
    inbound_profile: ContactProfile | None = None,
) -> Contact:
    """Contact for an inbound channel message, enriched via the platform if needed.

    ``fetch_profile`` is only called while something is still missing, so an active
    conversation costs one Graph API call, not one per message.
    """
    contact = await upsert_contact(
        session,
        organization_id=channel.organization_id,
        channel=channel.type,
        external_id=external_id,
        profile=inbound_profile,
    )
    if contact.display_name and contact.avatar_url:
        return contact
    try:
        fetched = await adapter.fetch_profile(channel, external_id)
    except Exception as exc:  # a profile lookup must never drop the message
        log.warning("contact_profile_fetch_failed", channel_type=channel.type, error=str(exc))
        return contact
    if fetched is None or fetched.is_empty():
        return contact
    return await upsert_contact(
        session,
        organization_id=channel.organization_id,
        channel=channel.type,
        external_id=external_id,
        profile=fetched,
    )
