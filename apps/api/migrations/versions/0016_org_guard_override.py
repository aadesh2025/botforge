"""Per-org override for the L2 injection classifier (docs/11 §4-L2)

Revision ID: 0016_org_guard_override
Revises: 0015_pii_guardrails
Create Date: 2026-08-04

Nullable on purpose: NULL means "follow the platform default", so an org that never touches
the setting keeps tracking `GUARD_INJECTION_ENABLED` instead of being frozen at whatever it
happened to be when the row was created. Only an explicit False is an opt-out.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016_org_guard_override"
down_revision: str | None = "0015_pii_guardrails"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "organizations", sa.Column("guard_injection_enabled", sa.Boolean(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("organizations", "guard_injection_enabled")
