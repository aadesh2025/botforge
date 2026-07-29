"""CrmContact — the canonical "this is one real human" record.

`Contact` is deliberately per-channel: the same person on Instagram and WhatsApp arrives
with two unrelated platform ids. This is the person-level layer above it, which its
docstring anticipated. Several `Contact` rows (one per channel someone has messaged from)
link to at most one `CrmContact`.

Matching is by **email or phone only**, never by name — names collide, vary in spelling,
and aren't unique. A wrong merge here silently mixes two customers' histories together,
which is far worse than leaving two records unmerged.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKey


class CrmContact(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "crm_contacts"
    __table_args__ = (
        # The two identity-resolution lookups, both run on every capture.
        Index("ix_crm_contacts_org_email", "organization_id", "email"),
        Index("ix_crm_contacts_org_phone", "organization_id", "phone"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    display_name: Mapped[str | None] = mapped_column(String(255))
    #: Stored lowercased so lookups are exact-match rather than case-sensitive misses.
    email: Mapped[str | None] = mapped_column(String(255))
    #: Stored E.164-ish (digits with a leading +) for the same reason.
    phone: Mapped[str | None] = mapped_column(String(32))

    # ── CRM fields, moved here from Contact: they describe the person, not a handle ──
    #: new|contacted|qualified|customer|lost
    lead_stage: Mapped[str | None] = mapped_column(String(32))
    #: Free text: what counts as an order status is business-specific.
    order_status: Mapped[str | None] = mapped_column(String(64))
    #: Same shape as Handoff.notes — {"by", "text", "at"}.
    notes: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, nullable=False)
    #: Same shape as Handoff.tags.
    labels: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
