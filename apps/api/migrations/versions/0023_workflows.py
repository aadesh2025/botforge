"""Visual workflow builder: workflows, workflow_versions, workflow_runs, workflow_steps

docs/17 Phase 2, ADR-074.

Mirrors `agents`/`agent_versions`' draft-publish shape via `use_alter` self-referencing FKs
(`workflows.current_version_id` -> `workflow_versions.id`, created after both tables exist) —
same reason `fk_agent_current_version` uses it: the two tables reference each other.

Revision ID: 0023_workflows
Revises: 0022_agentic_runtime
Create Date: 2026-08-19

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0023_workflows"
down_revision: str | None = "0022_agentic_runtime"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workflows",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "organization_id", sa.UUID(), sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("agent_id", sa.UUID(), sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("current_version_id", sa.UUID(), nullable=True),
        sa.Column("created_by", sa.UUID(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_workflows_organization_id", "workflows", ["organization_id"])
    op.create_index("ix_workflows_agent_id", "workflows", ["agent_id"])

    op.create_table(
        "workflow_versions",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("workflow_id", sa.UUID(), sa.ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), server_default="draft", nullable=False),
        sa.Column("graph", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("created_by", sa.UUID(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("workflow_id", "version"),
    )
    op.create_index("ix_workflow_versions_workflow_id", "workflow_versions", ["workflow_id"])

    op.create_foreign_key(
        "fk_workflow_current_version", "workflows", "workflow_versions",
        ["current_version_id"], ["id"],
    )

    op.create_table(
        "workflow_runs",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "workflow_version_id", sa.UUID(),
            sa.ForeignKey("workflow_versions.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "organization_id", sa.UUID(), sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "conversation_id", sa.UUID(), sa.ForeignKey("conversations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.String(24), server_default="running", nullable=False),
        sa.Column("current_node_id", sa.String(128), nullable=True),
        sa.Column("variables", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("budget", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_workflow_runs_workflow_version_id", "workflow_runs", ["workflow_version_id"])
    op.create_index("ix_workflow_runs_organization_id", "workflow_runs", ["organization_id"])

    op.create_table(
        "workflow_steps",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "workflow_run_id", sa.UUID(), sa.ForeignKey("workflow_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("node_id", sa.String(128), nullable=False),
        sa.Column("node_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("input", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("output", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_workflow_steps_workflow_run_id", "workflow_steps", ["workflow_run_id"])


def downgrade() -> None:
    op.drop_index("ix_workflow_steps_workflow_run_id", table_name="workflow_steps")
    op.drop_table("workflow_steps")
    op.drop_index("ix_workflow_runs_organization_id", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_workflow_version_id", table_name="workflow_runs")
    op.drop_table("workflow_runs")
    op.drop_constraint("fk_workflow_current_version", "workflows", type_="foreignkey")
    op.drop_index("ix_workflow_versions_workflow_id", table_name="workflow_versions")
    op.drop_table("workflow_versions")
    op.drop_index("ix_workflows_agent_id", table_name="workflows")
    op.drop_index("ix_workflows_organization_id", table_name="workflows")
    op.drop_table("workflows")
