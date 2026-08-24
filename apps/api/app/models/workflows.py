"""Visual workflow builder models (docs/17 Phase 2, §3).

Mirrors the `Agent`/`AgentVersion` draft-publish shape on purpose (`Workflow` is the stable
identity + a pointer to the live version; `WorkflowVersion` is the immutable, versioned graph)
rather than inventing a second pattern — see ADR-074. `WorkflowRun`/`WorkflowStep` are the
execution-side tables: one row per invocation and one row per node visited, so a paused or
failed run can be inspected and resumed without replaying anything already done.

Deliberately NOT built in this slice (see docs/PROGRESS.md's Phase 2 entry): Celery-driven
async execution, DB-persisted resume across a process restart (today's `graph.run_workflow`
executes synchronously in one call, matching Phase 1's `run_turn` shape at data-model level
but not yet wired to a broker), and the React Flow canvas.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKey


class Workflow(Base, UUIDPrimaryKey, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "workflows"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    # Nullable — docs/17 §3 allows a workflow to be agent-scoped or standalone (e.g. a
    # future scheduled/triggered automation with no chat agent behind it).
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("workflow_versions.id", use_alter=True, name="fk_workflow_current_version"),
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class WorkflowVersion(Base, UUIDPrimaryKey):
    __tablename__ = "workflow_versions"
    __table_args__ = (UniqueConstraint("workflow_id", "version"),)

    workflow_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflows.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    # draft|in_review|published|archived — mirrors AgentVersion's is_published but as a status
    # string rather than a bool, since docs/17 §7 Phase 4 (version/approval workflow) needs an
    # in_review state Phase 1's simpler draft/published split never needed.
    status: Mapped[str] = mapped_column(String(16), default="draft", nullable=False)
    # {"nodes": [{"id","type","config"}], "edges": [{"source","target","condition"}]} — see
    # docs/17 §3.1. Validated against `app.workflows.graph`'s node-type registry on write, not
    # just accepted as opaque JSON (a workflow that references an unknown node type must fail
    # at save time, not at first run).
    graph: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class WorkflowRun(Base, UUIDPrimaryKey):
    __tablename__ = "workflow_runs"

    workflow_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_versions.id", ondelete="CASCADE"), index=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL")
    )
    # running|paused_approval|completed|failed|cancelled|budget_exceeded
    status: Mapped[str] = mapped_column(String(24), default="running", nullable=False)
    # The node to resume from when status == paused_approval. NULL once the run finishes.
    current_node_id: Mapped[str | None] = mapped_column(String(128))
    variables: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    # {"max_steps","max_tool_calls","max_runtime_s","max_cost_usd","consumed_steps",
    #  "consumed_tool_calls","consumed_cost_usd","tripped"} — a serialized `AgentBudget`
    # (app.chat.budget), reused rather than reinvented; see ADR-074.
    budget: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    # docs/17 Phase 2 item 3: a run against the workflow's LATEST version (draft or published,
    # via the canvas's "Test run" button), distinguished from real production traffic. Executed
    # identically to a real run otherwise — no side-effect sandboxing, same trade-off the Agent
    # Playground already makes (real tool calls, real agent turns, real spend).
    is_test: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class WorkflowStep(Base, UUIDPrimaryKey):
    __tablename__ = "workflow_steps"

    workflow_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="CASCADE"), index=True
    )
    node_id: Mapped[str] = mapped_column(String(128), nullable=False)
    node_type: Mapped[str] = mapped_column(String(32), nullable=False)
    # pending|running|completed|failed|skipped|awaiting_approval
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    # Sanitized only — same rule as `agent_steps.tool_output` (docs/17 §2 rule 4): a tool
    # node's raw result never lands here, only what survived neutralize_injections().
    input: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    output: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[float | None] = mapped_column(Float)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
