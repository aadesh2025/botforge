"""Per-knowledge-base FTS language + the GIN indexes each configuration needs

docs/13 R4b, docs/14 K5-1.

`to_tsvector('english', ...)` was hardcoded, so for a Tamil or Hindi knowledge base the keyword
half of hybrid retrieval contributed nothing — English stemming over Tamil produces tokens that
match nothing. The retrieval-side twin of docs/11 §9.2a's "L1 is English-first" gap.

**The index is the part that is easy to get wrong.** `migrations/0004` created ONE expression
index, on `to_tsvector('english', content)`. An expression index matches only the exact
expression, so a knowledge base switched to `tamil` would render `to_tsvector('tamil', content)`
and silently fall back to a sequential scan over every chunk in the table — the same failure
P0-1 just fixed, reintroduced through the front door. docs/14 §5.4 says this explicitly: do not
change the regconfig and leave 0004's index behind.

One GIN index per configuration is the straightforward answer, and it is not free: each one
costs write time on every ingest and disk proportional to the corpus. So this creates indexes
only for the configurations actually reachable today — `english` (already there, from 0004) and
`simple` — and `app/rag/fts.py` documents that adding a language means adding its index.

Revision ID: 0019_kb_fts_config
Revises: 0018_user_is_system
Create Date: 2026-08-13

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019_kb_fts_config"
down_revision: str | None = "0018_user_is_system"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Configurations that get an index up front. Every existing KB is English, so `simple` is the
# only genuinely new one — it is the fallback any non-English KB will be pointed at first, and
# creating its index here means the first client to switch does not discover the seq scan.
_INDEXED_CONFIGS = ("simple",)


def upgrade() -> None:
    op.add_column(
        "knowledge_bases",
        sa.Column(
            "fts_config",
            sa.String(length=32),
            nullable=False,
            server_default="english",
        ),
    )
    for config in _INDEXED_CONFIGS:
        op.execute(
            f"CREATE INDEX IF NOT EXISTS ix_chunks_content_fts_{config} "
            f"ON chunks USING gin (to_tsvector('{config}', content))"
        )


def downgrade() -> None:
    for config in _INDEXED_CONFIGS:
        op.execute(f"DROP INDEX IF EXISTS ix_chunks_content_fts_{config}")
    op.drop_column("knowledge_bases", "fts_config")
