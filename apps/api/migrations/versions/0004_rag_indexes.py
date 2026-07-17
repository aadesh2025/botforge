"""RAG indexes: HNSW cosine index on chunk embeddings + GIN full-text index on content

Revision ID: 0004_rag_indexes
Revises: ef13a002b302
Create Date: 2026-07-17

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0004_rag_indexes"
down_revision: str | None = "ef13a002b302"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Approximate-nearest-neighbour index for cosine similarity retrieval (pgvector HNSW).
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_chunks_embedding_hnsw "
        "ON chunks USING hnsw (embedding vector_cosine_ops)"
    )
    # GIN index backing hybrid full-text (tsvector) ranking over chunk content.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_chunks_content_fts "
        "ON chunks USING gin (to_tsvector('english', content))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_chunks_content_fts")
    op.execute("DROP INDEX IF EXISTS ix_chunks_embedding_hnsw")
