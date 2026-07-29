"""Macros — a named, ordered list of inbox actions run against one conversation."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKey


class Macro(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "macros"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    #: Ordered. Each action: {"type": "reply"|"add_tag"|"assign"|"resolve", "params": {...}}
    #: Stored as JSONB rather than a child table: the list is short, always read and written
    #: whole, and never queried by its contents.
    actions: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
