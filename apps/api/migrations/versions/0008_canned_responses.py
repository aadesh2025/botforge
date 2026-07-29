"""Canned responses

Revision ID: 0008_canned_responses
Revises: 0007_last_inbound_at
Create Date: 2026-07-29

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_canned_responses"
down_revision: str | None = "0007_last_inbound_at"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "canned_responses",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.UUID(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("shortcut", sa.String(length=64), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_by", sa.UUID(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_canned_responses_organization_id", "canned_responses", ["organization_id"])
    # Shortcuts are typed, not picked — a duplicate would make the picker ambiguous.
    op.create_index(
        "ix_canned_responses_org_shortcut",
        "canned_responses",
        ["organization_id", "shortcut"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_canned_responses_org_shortcut", table_name="canned_responses")
    op.drop_index("ix_canned_responses_organization_id", table_name="canned_responses")
    op.drop_table("canned_responses")
