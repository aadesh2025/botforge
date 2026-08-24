"""Workflow regression testing models (docs/17 Phase 4 follow-up, ADR-081).

New tables, deliberately NOT a `workflow_id` column bolted onto `agent_tests`/`agent_test_runs`
— that table's shape (`input_message`, `scripted_tool_calls` fed into
`app.llm.fake.MultiRoundToolProvider`, `expected_final_answer_contains`) is intrinsically a
single chat-turn's "final answer" concept, which a workflow run does not have: a workflow's
outcome is a final `status` and a `variables` dict (`app.workflows.graph.WorkflowRunResult`),
not text. Reusing the table would mean half its columns are dead weight depending on which kind
of row it is — the exact anti-pattern ADR-079 already rejected once for `agent_steps`/
`WorkflowRun`. `WorkflowTest` mirrors `AgentTest`'s *pattern* (author-defined scenario, cached-
mode script, expected outcome) with columns shaped for a graph run instead of a chat turn.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKey


class WorkflowTest(Base, UUIDPrimaryKey):
    __tablename__ = "workflow_tests"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflows.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    # Seed `variables` the run starts with — a workflow run's only "input", no message/history
    # concept (that belongs to the `agent` node's own scripted content, not the workflow itself).
    input_variables: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    # Cached/replayed mode's script (mirrors AgentTest.scripted_tool_calls's role, ADR-081):
    # {"tools": {tool_name: {"output": dict, "status": str, "error": str|None}},
    #  "agents": {agent_id: {"content": str, "status": str, "error": str|None}},
    #  "sub_workflows": {workflow_id: {"status": str, "variables": dict, "error": str|None}}}
    # Keyed by what the node's real executor callback actually receives (tool_name / agent_id /
    # workflow_id) — graph.py's executors are never told which graph node_id called them, so a
    # graph-node_id key would be unusable here.
    scripted_node_outputs: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    # The assertions checked against the ACTUAL run, in both cached and live mode. `None`/empty
    # means "don't assert this dimension" — a test author names what matters, same as AgentTest.
    expected_status: Mapped[str | None] = mapped_column(String(24))
    expected_variables_contains: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    expected_visited_node_ids: Mapped[list[Any]] = mapped_column(JSONB, default=list, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class WorkflowTestRun(Base, UUIDPrimaryKey):
    __tablename__ = "workflow_test_runs"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflows.id", ondelete="CASCADE"), index=True
    )
    workflow_test_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_tests.id", ondelete="CASCADE"), index=True
    )
    # Groups every case triggered by the same POST /tests/run call — "the latest test run" for
    # the publish gate means the latest BATCH, exactly matching AgentTestRun's own rule.
    batch_id: Mapped[uuid.UUID] = mapped_column(index=True)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)  # cached | live
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # passed | failed | error
    actual_status: Mapped[str | None] = mapped_column(String(24))
    # Sanitized only, same rule as agent_steps.tool_output / AgentTestRun.actual_tool_calls
    # (docs/17 §2 rule 4) — but nothing extra to enforce here: every value that could reach
    # `variables` already passed through `neutralize_injections()` inside graph.py's own node
    # handlers (`_run_tool`/`_run_agent`/`_run_sub_agent`), for a real executor AND a scripted
    # one alike, since that call lives in the node handler, not the injected executor.
    actual_variables: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    actual_visited_node_ids: Mapped[list[Any]] = mapped_column(JSONB, default=list, nullable=False)
    failure_reasons: Mapped[list[Any]] = mapped_column(JSONB, default=list, nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[float | None] = mapped_column(Float)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
