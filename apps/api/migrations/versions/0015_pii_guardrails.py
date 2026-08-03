"""PII guardrails: org contact allowlist + per-document PII flags (docs/11 Phase B)

Revision ID: 0015_pii_guardrails
Revises: 0014_widget_configs
Create Date: 2026-08-03

`organizations.public_contacts` is the allowlist of contact details an agent may share; it is
NOT NULL with a `'[]'` default so an existing org is "shares nothing" rather than NULL, which
would have to be special-cased at every read.

`documents.pii_flags` is deliberately **nullable**: NULL means "never scanned" (every document
ingested before this migration) and `{}` means "scanned and clean". Collapsing those two into
one value would make the knowledge UI claim a document is clean when nobody has ever looked.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015_pii_guardrails"
down_revision: str | None = "0014_widget_configs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column(
            "public_contacts",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "documents",
        sa.Column("pii_flags", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("documents", "pii_flags")
    op.drop_column("organizations", "public_contacts")
