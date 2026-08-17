"""chunks.heading, and rebuild the FTS indexes over heading + content

docs/14 K2-6, ADR-067.

K2 moved a chunk's heading path into the *embedding* input and out of `chunks.content`. Measured
(docs/14 K2-5): dense NDCG@10 +0.0104, FTS **-0.0206**, fused hybrid net negative. The FTS index
is built over `content`, so "embedding input only" silently deleted the heading from the text the
keyword half searches. This is the lexical twin of `TextChunk.embed_text` — the heading informs
the search without being pasted into the citation text a visitor reads.

**The dangerous part of this migration is the index, not the column.** An expression index
matches only the exact expression, so changing what `fts_statement` renders *without* rebuilding
the indexes to match would leave every keyword query doing a sequential scan over every chunk in
the table. That is P0-1 exactly, and migration 0019's docstring warns about this same trap in the
regconfig dimension. `make explain-fts` is the check; it exits 1 if the expression stops matching.

Legacy chunks have `heading IS NULL`, and `coalesce(heading, '') || ' ' || content` differs from
`content` only by a leading space, which `to_tsvector` discards. So every existing chunk indexes
to the same tsvector it did before and no re-ingest is required — verified against the eval
corpus, where the legacy NDCG@10 is unchanged at 0.6487.

Revision ID: 0021_chunk_heading_fts
Revises: 0020_docling_extraction
Create Date: 2026-08-17

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021_chunk_heading_fts"
down_revision: str | None = "0020_docling_extraction"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Must match `app.rag.fts.SEARCHABLE_SQL` character for character.
_SEARCHABLE = "coalesce(heading, '') || ' ' || content"

# Same set as migration 0019: the configurations reachable today. Adding a language means
# adding its index here as well as to `fts.SUPPORTED_CONFIGS`, or that KB seq-scans.
_CONFIGS = ("english", "simple")

# 0004 and 0019 built these over `content` alone. They cannot serve the new expression, and
# leaving them costs write time on every ingest plus disk, for an expression nothing renders.
_SUPERSEDED = ("ix_chunks_content_fts", "ix_chunks_content_fts_simple")


def upgrade() -> None:
    op.add_column("chunks", sa.Column("heading", sa.Text(), nullable=True))
    for config in _CONFIGS:
        op.execute(
            f"CREATE INDEX IF NOT EXISTS ix_chunks_search_fts_{config} "
            f"ON chunks USING gin (to_tsvector('{config}', {_SEARCHABLE}))"
        )
    for name in _SUPERSEDED:
        op.execute(f"DROP INDEX IF EXISTS {name}")


def downgrade() -> None:
    # Recreate the old indexes before dropping the column they do not use, so a rolled-back
    # deployment is never left with no usable FTS index at all.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_chunks_content_fts "
        "ON chunks USING gin (to_tsvector('english', content))"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_chunks_content_fts_simple "
        "ON chunks USING gin (to_tsvector('simple', content))"
    )
    for config in _CONFIGS:
        op.execute(f"DROP INDEX IF EXISTS ix_chunks_search_fts_{config}")
    op.drop_column("chunks", "heading")
