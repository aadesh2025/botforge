"""Tools and tool-run logs."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKey


class Tool(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "tools"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    agent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    type: Mapped[str] = mapped_column(String(16), nullable=False)  # builtin|http|n8n
    description: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    input_schema: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class ToolRun(Base, UUIDPrimaryKey):
    __tablename__ = "tool_runs"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    tool_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tools.id", ondelete="CASCADE"), index=True)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("conversations.id", ondelete="SET NULL"))
    message_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("messages.id", ondelete="SET NULL"))
    input: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    output: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # success|error|timeout
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
