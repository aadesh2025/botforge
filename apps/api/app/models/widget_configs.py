"""Widget appearance — one row per agent, deliberately **not** versioned.

This used to live in `AgentVersion.persona.widget`, which meant a colour change rode the
same publish approval as a change to what the AI actually says. Those are not the same kind
of decision: a cosmetic tweak should be live the moment it's saved, exactly as the embed
snippet already promises ("saving here updates every embedded widget on the visitor's next
page load"). It only *looked* instant before because a never-published agent's latest draft
and its live version are the same thing by coincidence.

So: no draft, no publish, no version. A save is live.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKey


class WidgetConfig(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "widget_configs"

    agent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    #: The camelCase `WidgetConfigIn` shape the builder writes and `_theme()` reads.
    theme: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
