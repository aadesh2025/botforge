"""conversations.last_inbound_at (WhatsApp 24-hour window)

Revision ID: 0007_last_inbound_at
Revises: 0006_contacts
Create Date: 2026-07-29

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_last_inbound_at"
down_revision: str | None = "0006_contacts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("conversations", sa.Column("last_inbound_at", sa.DateTime(timezone=True), nullable=True))
    # Backfill from the newest user message so existing threads get a truthful window
    # state instead of reading as "never heard from" (which would block every reply).
    op.execute(
        """
        UPDATE conversations c
           SET last_inbound_at = m.max_created
        FROM (
            SELECT conversation_id, MAX(created_at) AS max_created
            FROM messages WHERE role = 'user' GROUP BY conversation_id
        ) m
        WHERE m.conversation_id = c.id
        """
    )


def downgrade() -> None:
    op.drop_column("conversations", "last_inbound_at")
