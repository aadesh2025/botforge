"""Agent regression testing models (docs/17 Phase 3, ADR-079).

New tables, not a reuse of `agent_steps`/`WorkflowRun` — `AgentTest` is an author-defined
scenario (what should happen), `AgentTestRun` is one execution's actual outcome checked against
it. Neither existing execution-trace table has any notion of an *expected* outcome.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKey


class AgentTest(Base, UUIDPrimaryKey):
    __tablename__ = "agent_tests"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    input_message: Mapped[str] = mapped_column(Text, nullable=False)
    # [{"role": "user"|"assistant", "content": str}, ...] — prior turns, for multi-turn scenarios.
    input_history: Mapped[list[Any]] = mapped_column(JSONB, default=list, nullable=False)
    # Cached/replayed mode's script (ADR-079) — [{"name": str, "arguments": dict}, ...], fed
    # directly into app.llm.fake.MultiRoundToolProvider's constructor shape.
    scripted_tool_calls: Mapped[list[Any]] = mapped_column(JSONB, default=list, nullable=False)
    scripted_final_answer: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # The assertion checked against the ACTUAL run, in both cached and live mode.
    # [{"name": str, "arguments": dict | None}, ...] — arguments None means "any", name-only match.
    expected_tool_calls: Mapped[list[Any]] = mapped_column(JSONB, default=list, nullable=False)
    expected_final_answer_contains: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AgentTestRun(Base, UUIDPrimaryKey):
    __tablename__ = "agent_test_runs"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), index=True)
    agent_test_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_tests.id", ondelete="CASCADE"), index=True
    )
    # Groups every case triggered by the same POST /tests/run call — "the latest test run" for
    # the publish gate means the latest BATCH, not one case's history read in isolation.
    batch_id: Mapped[uuid.UUID] = mapped_column(index=True)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)  # cached | live
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # passed | failed | error
    # Sanitized only — same rule as agent_steps.tool_output (docs/17 §2 rule 4).
    actual_tool_calls: Mapped[list[Any]] = mapped_column(JSONB, default=list, nullable=False)
    actual_final_answer: Mapped[str | None] = mapped_column(Text)
    failure_reasons: Mapped[list[Any]] = mapped_column(JSONB, default=list, nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[float | None] = mapped_column(Float)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
