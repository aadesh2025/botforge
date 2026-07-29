"""Canned responses — reusable reply snippets an operator inserts by shortcut."""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKey


class CannedResponse(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "canned_responses"
    __table_args__ = (
        # Shortcuts are typed, not picked, so two "/refund" entries in one org would make
        # the picker ambiguous.
        Index("ix_canned_responses_org_shortcut", "organization_id", "shortcut", unique=True),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    shortcut: Mapped[str] = mapped_column(String(64), nullable=False)  # e.g. "refund"
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
