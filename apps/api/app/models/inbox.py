"""Human handoff records."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKey


class Handoff(Base, UUIDPrimaryKey):
    __tablename__ = "handoffs"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    requested_by: Mapped[str] = mapped_column(String(16), nullable=False)  # bot|user
    reason: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="open", nullable=False)  # open|assigned|resolved
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    notes: Mapped[list[Any]] = mapped_column(JSONB, default=list, nullable=False)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    resolved_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
