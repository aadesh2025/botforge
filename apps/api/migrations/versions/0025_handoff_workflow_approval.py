"""handoffs.workflow_run_id + conversation_id nullable — docs/17 Phase 2 item 4

Approval nodes reuse the existing Handoff/inbox model (ADR — see docs/DECISIONS.md) rather than
a parallel "workflow approval" concept: `status` (open|assigned|resolved), `assigned_to`,
`notes` and `tags` all mean the same thing for a paused workflow as they do for a chat handoff.
`conversation_id` becomes nullable because a `WorkflowRun` is not always attached to one
(`workflow_runs.conversation_id` is itself nullable) — a standalone workflow with no chat agent
behind it can still pause on an Approval node and needs a Handoff row to surface in the inbox.

Revision ID: 0025_handoff_workflow_approval
Revises: 0024_workflow_run_is_test
Create Date: 2026-08-24

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025_handoff_workflow_approval"
down_revision: str | None = "0024_workflow_run_is_test"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("handoffs", "conversation_id", existing_type=sa.UUID(), nullable=True)
    op.add_column(
        "handoffs",
        sa.Column(
            "workflow_run_id", sa.UUID(),
            sa.ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=True,
        ),
    )
    op.create_index("ix_handoffs_workflow_run_id", "handoffs", ["workflow_run_id"])


def downgrade() -> None:
    op.drop_index("ix_handoffs_workflow_run_id", table_name="handoffs")
    op.drop_column("handoffs", "workflow_run_id")
    op.alter_column("handoffs", "conversation_id", existing_type=sa.UUID(), nullable=False)
