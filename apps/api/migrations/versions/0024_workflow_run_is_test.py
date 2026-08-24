"""workflow_runs.is_test — docs/17 Phase 2 item 3 (draft-version test-mode execution)

Distinguishes a test-run (against a workflow's latest, possibly-unpublished version, launched
from the canvas's "Test run" button) from a real production run. Persisted rather than kept
out-of-band: "can't see what happened on my last test run" is a worse default than one extra
column, and every other field on `workflow_runs`/`workflow_steps` is equally useful for a test
run (steps, budget spend, error) — a test run is a real execution, just one that should never
be confused with production traffic in a report.

Revision ID: 0024_workflow_run_is_test
Revises: 0023_workflows
Create Date: 2026-08-24

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024_workflow_run_is_test"
down_revision: str | None = "0023_workflows"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "workflow_runs",
        sa.Column("is_test", sa.Boolean(), server_default=sa.false(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("workflow_runs", "is_test")
