"""Contacts — the human on the other end of a conversation.

A contact is the *identity* (name, avatar, handle) behind a channel-specific id; a
conversation is one thread with that identity. Keeping them apart is what lets the
unified inbox show "Aadesh" with a photo instead of a raw PSID, and lets the same
person keep their identity across several conversations on the same channel.

Identity is scoped per channel on purpose: the same human on Instagram and on WhatsApp
arrives with two unrelated platform ids and no reliable way to link them. Cross-channel
merging lives *on top of* this table, in `CrmContact` (see `models/crm.py`) — which is
where the person-level fields (lead stage, notes, labels) now live too, since they describe
the human rather than one of their handles.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKey


class Contact(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "contacts"
    __table_args__ = (
        Index(
            "ix_contacts_org_channel_external",
            "organization_id",
            "channel",
            "external_id",
            unique=True,
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    # widget|telegram|whatsapp|instagram|facebook|slack|discord
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    # PSID, IGSID, chat_id, phone number, Slack user id, widget visitor id, …
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255))
    avatar_url: Mapped[str | None] = mapped_column(String(1024))
    # Whatever else the platform hands us: username, phone, email, locale.
    extra: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    #: The canonical person this handle belongs to, once we can tell. Null until an
    #: email/phone links it — most contacts never share either.
    crm_contact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("crm_contacts.id", ondelete="SET NULL")
    )
