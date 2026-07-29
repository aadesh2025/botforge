"""CRM fields on contacts (lead stage, order status, notes, labels)

Revision ID: 0010_contact_crm
Revises: 0009_macros
Create Date: 2026-07-29

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_contact_crm"
down_revision: str | None = "0009_macros"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("contacts", sa.Column("lead_stage", sa.String(length=32), nullable=True))
    op.add_column("contacts", sa.Column("order_status", sa.String(length=64), nullable=True))
    op.add_column(
        "contacts",
        sa.Column(
            "notes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "contacts",
        sa.Column(
            "labels",
            postgresql.ARRAY(sa.String()),
            server_default=sa.text("'{}'::varchar[]"),
            nullable=False,
        ),
    )
    # The CRM list filters on these two; everything else is a substring name search.
    op.create_index("ix_contacts_org_lead_stage", "contacts", ["organization_id", "lead_stage"])
    op.create_index("ix_contacts_labels", "contacts", ["labels"], postgresql_using="gin")


def downgrade() -> None:
    op.drop_index("ix_contacts_labels", table_name="contacts")
    op.drop_index("ix_contacts_org_lead_stage", table_name="contacts")
    op.drop_column("contacts", "labels")
    op.drop_column("contacts", "notes")
    op.drop_column("contacts", "order_status")
    op.drop_column("contacts", "lead_stage")
