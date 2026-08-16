"""Track which extractor produced a document, and where its structured form lives

docs/14 K1-4, §6.

Two columns, and the reasons are different:

`extraction_backend` makes a re-ingest campaign **targetable** and a quality regression
**attributable**. Rollout (docs/14 §12) enables Docling for new documents while every existing
chunk stays as it was, so a mixed corpus is the expected state for as long as the backfill
takes. Without this column there is no way to ask "which documents still need re-ingesting?"
or "did the ones we converted get better?" — the questions the whole phase exists to answer.

`docling_json_path` is a **path, not the JSON**. docs/14 §6 is explicit: these blobs carry
per-element geometry, provenance and table cells, so a big PDF produces a large one. Putting
that in a `jsonb` column bloats the table every tenant query touches and pushes backup size up
fast. Same shape as `documents.storage_path`, which already exists and already works.

Nullable on purpose. NULL means "no structured form" — a legacy-extracted document, or one
Docling handled before persistence was switched on — and every consumer has to read it
defensively rather than assume the re-chunk path is available.

Revision ID: 0020_docling_extraction
Revises: 0019_kb_fts_config
Create Date: 2026-08-13

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020_docling_extraction"
down_revision: str | None = "0019_kb_fts_config"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column(
            "extraction_backend",
            sa.String(length=16),
            nullable=False,
            # Every existing row was extracted by the legacy path. Backfilling it as `legacy`
            # rather than NULL is the honest record: we know exactly what produced them.
            server_default="legacy",
        ),
    )
    op.add_column("documents", sa.Column("docling_json_path", sa.String(length=1024), nullable=True))
    # The backfill campaign selects on this, so it needs to be cheap on a large documents table.
    op.create_index(
        "ix_documents_extraction_backend", "documents", ["organization_id", "extraction_backend"]
    )


def downgrade() -> None:
    op.drop_index("ix_documents_extraction_backend", table_name="documents")
    op.drop_column("documents", "docling_json_path")
    op.drop_column("documents", "extraction_backend")
