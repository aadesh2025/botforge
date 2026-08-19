"""Org-scoped MCP server registrations (docs/17 Phase 1, §4)."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKey


class MCPServer(Base, UUIDPrimaryKey, TimestampMixin):
    """One org's registered MCP server. Never resolved against another org's credentials —
    same rule ADR-055 established for guard models and ADR-047/048 for provider keys."""

    __tablename__ = "mcp_servers"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    transport: Mapped[str] = mapped_column(String(16), nullable=False)  # stdio | sse
    # stdio: the command to spawn. sse: the server URL.
    url_or_command: Mapped[str] = mapped_column(Text, nullable=False)
    # Encrypted JSON (app.core.crypto): {"args": [...], "env": {...}, "headers": {...}}.
    # Never plaintext at rest — this can carry a bearer token or subprocess env secrets.
    auth_config_enc: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
