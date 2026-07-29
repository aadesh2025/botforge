"""Campaigns — proactive outbound messages.

Two very different things share the name, and only one of them is safe to ship as-is:

- ``widget_trigger``: a message the embedded widget shows unprompted after a client-side
  condition (time on page, URL match). No external channel, no consent question — the
  visitor is already on the site.
- ``broadcast``: sending to many contacts on WhatsApp/etc. That needs consent tracking, an
  unsubscribe path, rate-limited batch sending, and (outside WhatsApp's 24-hour window)
  approved templates. Until that exists, broadcasts are **draft-only and cannot send** —
  see `docs/DECISIONS.md` ADR-039.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKey

KINDS = ("widget_trigger", "broadcast")
STATUSES = ("draft", "active", "paused")


class Campaign(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "campaigns"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # widget_trigger | broadcast
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    #: widget_trigger: {"delay_seconds": int, "url_pattern": str}
    trigger_config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="draft", nullable=False)
