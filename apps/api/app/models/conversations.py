"""Conversations and messages."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKey


class Conversation(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "conversations"
    __table_args__ = (Index("ix_conversations_agent_last_msg", "agent_id", "last_message_at"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), index=True)
    channel: Mapped[str] = mapped_column(String(16), nullable=False)  # web|widget|api|telegram|...
    channel_user_id: Mapped[str | None] = mapped_column(String(255))
    external_id: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str | None] = mapped_column(String(512))
    meta: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict, nullable=False)
    memory_summary: Mapped[str | None] = mapped_column(Text)
    last_message_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class Message(Base, UUIDPrimaryKey):
    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_conversation_created", "conversation_id", "created_at"),)

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # user|assistant|system|tool
    content: Mapped[str | None] = mapped_column(Text)
    tool_calls: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    tool_call_id: Mapped[str | None] = mapped_column(String(255))
    citations: Mapped[list[Any]] = mapped_column(JSONB, default=list, nullable=False)
    provider: Mapped[str | None] = mapped_column(String(32))
    model: Mapped[str | None] = mapped_column(String(128))
    tokens_prompt: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tokens_completion: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_micros: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
