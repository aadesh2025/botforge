"""Channel connections (widget, telegram, whatsapp, slack, discord, api)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKey


class Channel(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "channels"
    __table_args__ = (Index("ix_channels_org_type", "organization_id", "type"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(16), nullable=False)  # widget|telegram|whatsapp|slack|discord|api
    name: Mapped[str | None] = mapped_column(String(255))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    webhook_secret: Mapped[str | None] = mapped_column(String(255))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
