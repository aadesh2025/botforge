"""Attention queue: conversation flags + attention level (docs/11 §L6, Phase E)

Revision ID: 0017_conversation_flags
Revises: 0016_org_guard_override
Create Date: 2026-08-04

`attention_level` is a separate column rather than a new `status` value (ADR-057): status is a
lifecycle and attention is a severity that coexists with it. A crisis a human has taken over is
still a crisis; folding the two would erase that on takeover.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017_conversation_flags"
down_revision: str | None = "0016_org_guard_override"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("conversations", sa.Column("attention_level", sa.String(16), nullable=True))
    op.create_table(
        "conversation_flags",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column(
            "signals",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_index("ix_conversation_flags_organization_id", "conversation_flags", ["organization_id"])
    op.create_index("ix_conversation_flags_conversation_id", "conversation_flags", ["conversation_id"])
    op.create_index("ix_conversation_flags_org_open", "conversation_flags", ["organization_id", "resolved_at"])


def downgrade() -> None:
    op.drop_table("conversation_flags")
    op.drop_column("conversations", "attention_level")
