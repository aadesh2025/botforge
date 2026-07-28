"""Contacts table + conversations.contact_id (unified multi-channel inbox)

Revision ID: 0006_contacts
Revises: 0005_feature_flags
Create Date: 2026-07-28

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_contacts"
down_revision: str | None = "0005_feature_flags"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "contacts",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.UUID(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("channel", sa.String(length=16), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("avatar_url", sa.String(length=1024), nullable=True),
        sa.Column(
            "extra",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_contacts_organization_id", "contacts", ["organization_id"])
    # One identity per (org, channel, platform id) — the key every adapter upserts on.
    op.create_index(
        "ix_contacts_org_channel_external",
        "contacts",
        ["organization_id", "channel", "external_id"],
        unique=True,
    )

    op.add_column("conversations", sa.Column("contact_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_conversations_contact_id",
        "conversations",
        "contacts",
        ["contact_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_conversations_contact_id", "conversations", type_="foreignkey")
    op.drop_column("conversations", "contact_id")
    op.drop_index("ix_contacts_org_channel_external", table_name="contacts")
    op.drop_index("ix_contacts_organization_id", table_name="contacts")
    op.drop_table("contacts")
