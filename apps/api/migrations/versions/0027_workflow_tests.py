"""workflow_tests + workflow_test_runs -- docs/17 Phase 4 follow-up: workflow test-failure
publish gate (ADR-081)

New tables, not a `workflow_id` column on `agent_tests`/`agent_test_runs` -- that table's shape
(input_message, scripted_tool_calls, expected_final_answer_contains) is a chat-turn "final
answer" concept a workflow run does not have (its outcome is a status + variables dict). See
ADR-081 for the full reasoning, mirroring ADR-079's own precedent for not reusing
agent_steps/WorkflowRun.

Revision ID: 0027_workflow_tests
Revises: 0026_agent_tests
Create Date: 2026-08-24

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0027_workflow_tests"
down_revision: str | None = "0026_agent_tests"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workflow_tests",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "organization_id", sa.UUID(), sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("workflow_id", sa.UUID(), sa.ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("input_variables", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        # The cached/replayed mode's script (ADR-081), keyed by tool_name/agent_id/workflow_id --
        # what a node's real executor callback actually receives, not a graph node_id.
        sa.Column(
            "scripted_node_outputs", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column("expected_status", sa.String(24), nullable=True),
        sa.Column(
            "expected_variables_contains", postgresql.JSONB(astext_type=sa.Text()), server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "expected_visited_node_ids", postgresql.JSONB(astext_type=sa.Text()), server_default="[]",
            nullable=False,
        ),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_by", sa.UUID(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_workflow_tests_organization_id", "workflow_tests", ["organization_id"])
    op.create_index("ix_workflow_tests_workflow_id", "workflow_tests", ["workflow_id"])

    op.create_table(
        "workflow_test_runs",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "organization_id", sa.UUID(), sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("workflow_id", sa.UUID(), sa.ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "workflow_test_id", sa.UUID(), sa.ForeignKey("workflow_tests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Groups every case triggered by the same POST /tests/run call -- "the latest test run"
        # for the publish gate means the latest BATCH, exactly matching agent_test_runs.
        sa.Column("batch_id", sa.UUID(), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False),  # cached | live
        sa.Column("status", sa.String(16), nullable=False),  # passed | failed | error
        sa.Column("actual_status", sa.String(24), nullable=True),
        sa.Column(
            "actual_variables", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column(
            "actual_visited_node_ids", postgresql.JSONB(astext_type=sa.Text()), server_default="[]",
            nullable=False,
        ),
        sa.Column("failure_reasons", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_workflow_test_runs_organization_id", "workflow_test_runs", ["organization_id"])
    op.create_index("ix_workflow_test_runs_workflow_id", "workflow_test_runs", ["workflow_id"])
    op.create_index("ix_workflow_test_runs_workflow_test_id", "workflow_test_runs", ["workflow_test_id"])
    op.create_index("ix_workflow_test_runs_batch_id", "workflow_test_runs", ["batch_id"])


def downgrade() -> None:
    op.drop_index("ix_workflow_test_runs_batch_id", table_name="workflow_test_runs")
    op.drop_index("ix_workflow_test_runs_workflow_test_id", table_name="workflow_test_runs")
    op.drop_index("ix_workflow_test_runs_workflow_id", table_name="workflow_test_runs")
    op.drop_index("ix_workflow_test_runs_organization_id", table_name="workflow_test_runs")
    op.drop_table("workflow_test_runs")
    op.drop_index("ix_workflow_tests_workflow_id", table_name="workflow_tests")
    op.drop_index("ix_workflow_tests_organization_id", table_name="workflow_tests")
    op.drop_table("workflow_tests")
