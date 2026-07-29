"""CrmContact (canonical person) + move CRM fields off Contact + auto-capture toggle

Revision ID: 0013_crm_contacts
Revises: 0012_campaigns
Create Date: 2026-07-29

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013_crm_contacts"
down_revision: str | None = "0012_campaigns"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "crm_contacts",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.UUID(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("lead_stage", sa.String(length=32), nullable=True),
        sa.Column("order_status", sa.String(length=64), nullable=True),
        sa.Column(
            "notes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "labels",
            postgresql.ARRAY(sa.String()),
            server_default=sa.text("'{}'::varchar[]"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_crm_contacts_organization_id", "crm_contacts", ["organization_id"])
    # The two identity-resolution lookups, both run on every capture.
    op.create_index("ix_crm_contacts_org_email", "crm_contacts", ["organization_id", "email"])
    op.create_index("ix_crm_contacts_org_phone", "crm_contacts", ["organization_id", "phone"])

    op.add_column("contacts", sa.Column("crm_contact_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_contacts_crm_contact_id", "contacts", "crm_contacts", ["crm_contact_id"], ["id"],
        ondelete="SET NULL",
    )

    # Backfill: any contact that already carries CRM data becomes a person record, so no
    # operator's lead stages, notes or labels are lost when the columns move.
    op.execute(
        """
        WITH moved AS (
            INSERT INTO crm_contacts (
                id, organization_id, display_name, email, phone,
                lead_stage, order_status, notes, labels, created_at, updated_at
            )
            SELECT
                gen_random_uuid(),
                c.organization_id,
                c.display_name,
                lower(nullif(c.extra->>'email', '')),
                nullif(c.extra->>'phone', ''),
                c.lead_stage,
                c.order_status,
                c.notes,
                c.labels,
                c.created_at,
                c.updated_at
            FROM contacts c
            WHERE c.lead_stage IS NOT NULL
               OR c.order_status IS NOT NULL
               OR jsonb_array_length(c.notes) > 0
               OR array_length(c.labels, 1) > 0
            RETURNING id, organization_id, created_at, display_name
        )
        UPDATE contacts c
           SET crm_contact_id = m.id
          FROM moved m
         WHERE c.organization_id = m.organization_id
           AND c.created_at = m.created_at
           AND c.display_name IS NOT DISTINCT FROM m.display_name
        """
    )

    op.drop_column("contacts", "labels")
    op.drop_column("contacts", "notes")
    op.drop_column("contacts", "order_status")
    op.drop_column("contacts", "lead_stage")

    op.add_column(
        "organizations",
        sa.Column(
            "auto_crm_capture_enabled", sa.Boolean(), server_default=sa.true(), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_column("organizations", "auto_crm_capture_enabled")

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
    # Copy the person-level data back down onto each linked handle.
    op.execute(
        """
        UPDATE contacts c
           SET lead_stage = k.lead_stage,
               order_status = k.order_status,
               notes = k.notes,
               labels = k.labels
          FROM crm_contacts k
         WHERE c.crm_contact_id = k.id
        """
    )

    op.drop_constraint("fk_contacts_crm_contact_id", "contacts", type_="foreignkey")
    op.drop_column("contacts", "crm_contact_id")
    op.drop_index("ix_crm_contacts_org_phone", table_name="crm_contacts")
    op.drop_index("ix_crm_contacts_org_email", table_name="crm_contacts")
    op.drop_index("ix_crm_contacts_organization_id", table_name="crm_contacts")
    op.drop_table("crm_contacts")
