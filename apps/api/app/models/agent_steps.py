"""The per-turn agentic-loop trace (docs/17 Phase 1, §3). Separate from `workflow_steps`
(Phase 2, not built yet) — this is a single conversational turn's think/tool_call/final_answer
sequence, not a workflow-graph run.

Only ever written for turns the agentic runtime (docs/17 §2 flag) actually ran — see
`app.chat.runtime.run_turn`'s `budget is not None` guard. `tool_input`/`tool_output` are the
post-guard, post-redaction values only (rule §2.4): the same nullable-vs-scanned-clean
discipline `documents.pii_flags` already follows, never a raw tool result "for debugging."
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKey


class AgentStep(Base, UUIDPrimaryKey):
    __tablename__ = "agent_steps"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    # Nullable because it's written from `TurnResult.agent_steps` only after the assistant
    # `Message` row exists (see `_persist_agent_steps`); SET NULL rather than CASCADE so a
    # message edit/redaction elsewhere never silently deletes the trace.
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL")
    )
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # think|tool_call|final_answer
    tool_name: Mapped[str | None] = mapped_column(String(128))
    tool_input: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    tool_output: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    tokens_in: Mapped[int | None] = mapped_column(Integer)
    tokens_out: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # completed|failed|budget_exceeded
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
