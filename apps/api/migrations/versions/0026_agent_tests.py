"""agent_tests + agent_test_runs — docs/17 Phase 3 (Agent Testing)

New tables, not a reuse of `agent_steps`/`WorkflowRun` (ADR-079): `agent_tests` is an
author-defined scenario (input, scripted model behavior for cached-mode replay, expected
outcome to assert against); `agent_test_runs` is one scenario's one execution's actual-vs-
expected result. Neither existing execution-trace table has any notion of an *expected*
outcome to diff against.

Revision ID: 0026_agent_tests
Revises: 0025_handoff_workflow_approval
Create Date: 2026-08-24

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0026_agent_tests"
down_revision: str | None = "0025_handoff_workflow_approval"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_tests",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "organization_id", sa.UUID(), sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("agent_id", sa.UUID(), sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("input_message", sa.Text(), nullable=False),
        sa.Column("input_history", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        # The cached/replayed mode's script (ADR-079): fed directly into
        # app.llm.fake.MultiRoundToolProvider's constructor shape.
        sa.Column(
            "scripted_tool_calls", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False
        ),
        sa.Column("scripted_final_answer", sa.Text(), server_default="", nullable=False),
        # The assertion to check the ACTUAL run against, in both cached and live mode.
        sa.Column(
            "expected_tool_calls", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False
        ),
        sa.Column("expected_final_answer_contains", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_by", sa.UUID(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_agent_tests_organization_id", "agent_tests", ["organization_id"])
    op.create_index("ix_agent_tests_agent_id", "agent_tests", ["agent_id"])

    op.create_table(
        "agent_test_runs",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "organization_id", sa.UUID(), sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("agent_id", sa.UUID(), sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "agent_test_id", sa.UUID(), sa.ForeignKey("agent_tests.id", ondelete="CASCADE"), nullable=False
        ),
        # Groups every case triggered by the same POST /tests/run call — "the latest test run"
        # for the publish gate means the latest BATCH, not one case's history in isolation.
        sa.Column("batch_id", sa.UUID(), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False),  # cached | live
        sa.Column("status", sa.String(16), nullable=False),  # passed | failed | error
        sa.Column(
            "actual_tool_calls", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False
        ),
        sa.Column("actual_final_answer", sa.Text(), nullable=True),
        sa.Column("failure_reasons", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_agent_test_runs_organization_id", "agent_test_runs", ["organization_id"])
    op.create_index("ix_agent_test_runs_agent_id", "agent_test_runs", ["agent_id"])
    op.create_index("ix_agent_test_runs_agent_test_id", "agent_test_runs", ["agent_test_id"])
    op.create_index("ix_agent_test_runs_batch_id", "agent_test_runs", ["batch_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_test_runs_batch_id", table_name="agent_test_runs")
    op.drop_index("ix_agent_test_runs_agent_test_id", table_name="agent_test_runs")
    op.drop_index("ix_agent_test_runs_agent_id", table_name="agent_test_runs")
    op.drop_index("ix_agent_test_runs_organization_id", table_name="agent_test_runs")
    op.drop_table("agent_test_runs")
    op.drop_index("ix_agent_tests_agent_id", table_name="agent_tests")
    op.drop_index("ix_agent_tests_organization_id", table_name="agent_tests")
    op.drop_table("agent_tests")
