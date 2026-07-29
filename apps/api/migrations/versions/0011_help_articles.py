"""Help Center articles

Revision ID: 0011_help_articles
Revises: 0010_contact_crm
Create Date: 2026-07-29

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_help_articles"
down_revision: str | None = "0010_contact_crm"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "help_articles",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.UUID(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("agent_id", sa.UUID(), sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("body_markdown", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=128), nullable=True),
        sa.Column("published", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("sync_to_kb", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column(
            "kb_document_id", sa.UUID(), sa.ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_help_articles_organization_id", "help_articles", ["organization_id"])
    # Slugs address articles in public URLs.
    op.create_index("ix_help_articles_agent_slug", "help_articles", ["agent_id", "slug"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_help_articles_agent_slug", table_name="help_articles")
    op.drop_index("ix_help_articles_organization_id", table_name="help_articles")
    op.drop_table("help_articles")
