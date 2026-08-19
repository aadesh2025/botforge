"""Agentic runtime: mcp_servers, agent_steps, and the per-org loop flag

docs/17 Phase 1, ADR-070/ADR-073.

`organizations.agentic_loop_enabled` is nullable and, unlike `guard_injection_enabled`,
NULL/False both mean "off" — see the column's docstring in app/models/identity.py and
`app.chat.budget.agentic_loop_enabled` for why the polarity is deliberately reversed here.

Revision ID: 0022_agentic_runtime
Revises: 0021_chunk_heading_fts
Create Date: 2026-08-19

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0022_agentic_runtime"
down_revision: str | None = "0021_chunk_heading_fts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "organizations", sa.Column("agentic_loop_enabled", sa.Boolean(), nullable=True)
    )

    op.create_table(
        "mcp_servers",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.UUID(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("transport", sa.String(16), nullable=False),
        sa.Column("url_or_command", sa.Text(), nullable=False),
        sa.Column("auth_config_enc", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_by", sa.UUID(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_mcp_servers_organization_id", "mcp_servers", ["organization_id"])

    op.create_table(
        "agent_steps",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.UUID(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "conversation_id",
            sa.UUID(),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "message_id", sa.UUID(), sa.ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("step_index", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("tool_name", sa.String(128), nullable=True),
        sa.Column("tool_input", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("tool_output", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("tokens_in", sa.Integer(), nullable=True),
        sa.Column("tokens_out", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_agent_steps_organization_id", "agent_steps", ["organization_id"])
    op.create_index("ix_agent_steps_conversation_id", "agent_steps", ["conversation_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_steps_conversation_id", table_name="agent_steps")
    op.drop_index("ix_agent_steps_organization_id", table_name="agent_steps")
    op.drop_table("agent_steps")
    op.drop_index("ix_mcp_servers_organization_id", table_name="mcp_servers")
    op.drop_table("mcp_servers")
    op.drop_column("organizations", "agentic_loop_enabled")
