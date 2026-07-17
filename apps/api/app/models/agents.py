"""Agent, versioning, and provider-credential models."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKey


class Agent(Base, UUIDPrimaryKey, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "agents"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(String(1024))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)  # draft|published|archived
    public_key: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("agent_versions.id", use_alter=True, name="fk_agent_current_version")
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class AgentVersion(Base, UUIDPrimaryKey):
    __tablename__ = "agent_versions"
    __table_args__ = (UniqueConstraint("agent_id", "version"),)

    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    system_prompt: Mapped[str | None] = mapped_column(Text)
    persona: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    welcome_message: Mapped[str | None] = mapped_column(Text)
    fallback_message: Mapped[str | None] = mapped_column(Text)
    suggested_prompts: Mapped[list[Any]] = mapped_column(JSONB, default=list, nullable=False)
    model_config_json: Mapped[dict[str, Any]] = mapped_column(
        "model_config", JSONB, default=dict, nullable=False
    )
    rag_config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    features: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ProviderCredential(Base, UUIDPrimaryKey, TimestampMixin):
    """BYO API keys, per org or per agent. Keys stored encrypted."""

    __tablename__ = "provider_credentials"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    agent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    label: Mapped[str | None] = mapped_column(String(255))
    api_key_enc: Mapped[str | None] = mapped_column(String)
    base_url: Mapped[str | None] = mapped_column(String(1024))
    extra: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
