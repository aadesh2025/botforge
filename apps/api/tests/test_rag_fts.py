"""P0-1 — the FTS regconfig must render as a literal, or the GIN index cannot match.

`scripts/explain_fts.py` proves the *plan* against a populated database; this file pins the
*SQL*, so a future refactor back to `func.to_tsvector("english", ...)` fails in CI instead of
quietly returning the whole `chunks` table to a sequential scan on a long-lived connection.

See `app/rag/fts.py` for the measured EXPLAIN and why a custom plan hides this in dev.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from sqlalchemy import select, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Chunk
from app.rag import fts
from app.rag.retrieval import fts_statement

#: The migration that owns the FTS index expression. Named, not globbed, so replacing it means
#: deciding what the new one is rather than the test quietly following whatever landed last.
_MIGRATION = "0021_chunk_heading_fts.py"


def _compiled(config: str | None = None) -> str:
    stmt = fts_statement(uuid.uuid4(), [uuid.uuid4()], "refund policy", 20, config)
    return str(stmt.compile(dialect=postgresql.dialect()))


# ── the literal, which is the entire point ───────────────────────────────────────────────

def test_regconfig_renders_as_a_literal_not_a_bind_parameter() -> None:
    sql = _compiled()
    assert "'english'::regconfig" in sql
    # The pre-P0-1 shape. `to_tsvector(%(to_tsvector_1)s, ...)` is what made Postgres fall back
    # to a Seq Scan under a generic plan even with enable_seqscan=off.
    assert "to_tsvector(%(to_tsvector" not in sql
    assert "plainto_tsquery(%(plainto_tsquery" not in sql


def test_the_query_text_stays_parameterised() -> None:
    """Only the *config* is inlined. Inlining the query text would be an injection."""
    sql = _compiled()
    assert "refund policy" not in sql
    assert "plainto_tsquery('english'::regconfig, %(" in sql


# ── any-term, not all-terms ──────────────────────────────────────────────────────────────

def test_the_tsquery_matches_any_term_not_all_of_them() -> None:
    """`plainto_tsquery` alone ANDs every lexeme, which made the keyword half score 1/36.

    A customer types a sentence, not keywords: "ordered a kurta to delhi last week and it
    doesn't suit me, how long have i got" becomes nine `&`-joined stems and matches no chunk.
    With nothing coming back from FTS, RRF had a single list to fuse and `hybrid` was
    byte-identical to `dense` — the hybrid retrieval this product advertises was dense-only.
    """
    stmt = fts_statement(uuid.uuid4(), [uuid.uuid4()], "refund policy", 20, None)
    compiled = stmt.compile(dialect=postgresql.dialect())
    assert "replace(CAST(plainto_tsquery(" in str(compiled)
    assert "AS TSQUERY)" in str(compiled)
    # `&` and `|` are bind parameters, which is right — they are values, not identifiers, so
    # only the parameters can say which substitution is actually being made.
    scalars = {v for v in compiled.params.values() if isinstance(v, str)}
    assert {"&", "|"} <= scalars


def test_the_ranking_has_a_deterministic_tie_break() -> None:
    """`ORDER BY rank DESC` alone makes the same question answer differently on the same data.

    `ts_rank` is coarse and the any-term query makes ties the normal case, so without a second
    sort key Postgres returns tied chunks in physical row order and `LIMIT` keeps a different
    set each time. Running the eval harness's `fts` variant four times over an unchanged corpus
    gave 0.6247, 0.6247, 0.6220, 0.6397 — a spread wider than any effect docs/14 K2 was trying
    to measure, and wider than the 0.02 tolerance CI fails a regression on.
    """
    stmt = fts_statement(uuid.uuid4(), [uuid.uuid4()], "refund policy", 20, None)
    sql = str(stmt.compile(dialect=postgresql.dialect()))
    order_by = sql[sql.rindex("ORDER BY") :]
    assert "chunks.id" in order_by, order_by


async def test_tied_ranks_come_back_in_the_same_order_every_time(
    db_session: AsyncSession,
) -> None:
    """The rendered SQL is not the behaviour — ask a real Postgres, twice."""
    import uuid as _uuid

    from app.models import Chunk, Document, KnowledgeBase, Organization

    org = Organization(name="Tie Org", slug=f"tie-{_uuid.uuid4().hex[:8]}")
    db_session.add(org)
    await db_session.flush()
    kb = KnowledgeBase(organization_id=org.id, name="KB")
    db_session.add(kb)
    await db_session.flush()
    doc = Document(
        knowledge_base_id=kb.id,
        organization_id=org.id,
        source_type="text",
        filename="tie.txt",
        status="ready",
    )
    db_session.add(doc)
    await db_session.flush()
    # Identical text, so `ts_rank` is identical and only the tie-break can order them.
    for i in range(12):
        db_session.add(
            Chunk(
                document_id=doc.id,
                knowledge_base_id=kb.id,
                organization_id=org.id,
                ordinal=i,
                content="refund policy for international orders",
            )
        )
    await db_session.flush()

    async def _ids() -> list[str]:
        rows = await db_session.execute(fts_statement(org.id, [kb.id], "refund", 5, None))
        return [str(row[0].id) for row in rows.all()]

    assert await _ids() == await _ids()


async def test_any_term_tsquery_ors_its_lexemes_on_a_real_postgres(
    db_session: AsyncSession,
) -> None:
    """Rendered SQL is not behaviour. Ask the server what the tsquery actually is."""
    rendered = (
        await db_session.execute(
            text(
                "SELECT replace(plainto_tsquery('english', :q)::text, '&', '|')::tsquery::text"
            ),
            {"q": "how long for a refund on international orders"},
        )
    ).scalar_one()
    assert "|" in rendered
    assert "&" not in rendered


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        # `&` is a separator, never part of a lexeme, so the substitution cannot corrupt one.
        ("R&D budget & cost", "'r' | 'd' | 'budget' | 'cost'"),
        # Stopword-only and empty input produce an empty tsquery that matches nothing, rather
        # than an error on a visitor's turn.
        ("the and of", ""),
        ("", ""),
    ],
)
async def test_the_substitution_survives_the_inputs_that_would_break_it(
    db_session: AsyncSession, query: str, expected: str
) -> None:
    rendered = (
        await db_session.execute(
            text("SELECT replace(plainto_tsquery('english', :q)::text, '&', '|')::tsquery::text"),
            {"q": query},
        )
    ).scalar_one()
    assert rendered == expected


def test_a_non_default_config_reaches_the_sql() -> None:
    assert "'tamil'::regconfig" in _compiled("tamil")


# ── the allowlist is what makes inlining safe ────────────────────────────────────────────

@pytest.mark.parametrize(
    "hostile",
    [
        "english'); drop table chunks; --",
        "english' union select 1 --",
        "'; select pg_sleep(10); --",
        "../../etc/passwd",
        "en glish",
    ],
)
def test_an_unlisted_config_can_never_reach_the_sql(hostile: str) -> None:
    """`fts_config` becomes operator-settable, and it lands where no bind parameter can go.

    The defence is the allowlist, not escaping: anything outside `SUPPORTED_CONFIGS` normalises
    to the default before it is ever interpolated.
    """
    sql = _compiled(hostile)
    assert "'english'::regconfig" in sql
    assert "drop table" not in sql.lower()
    assert "pg_sleep" not in sql.lower()


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("english", "english"),
        ("  TAMIL  ", "tamil"),
        ("Simple", "simple"),
        ("", "english"),
        (None, "english"),
        ("klingon", "english"),
    ],
)
def test_normalize_config(given: str | None, expected: str) -> None:
    assert fts.normalize_config(given) == expected


# ── the doc correction, pinned ───────────────────────────────────────────────────────────

def test_tamil_and_hindi_are_supported() -> None:
    """docs/13 R4b and docs/14 §5.4 both claim Postgres ships no Tamil or Hindi dictionary.

    PostgreSQL 16 ships both. This matters commercially rather than academically: Tamil is a
    first language in this market (docs/11 §9.2a), and `tamil` genuinely stems
    (`கொள்கைகள்` -> `கொள்கை`) where `simple` only tokenises. If a future Postgres drops them
    this test goes red and the docs get corrected back, rather than a KB silently degrading.
    """
    assert {"tamil", "hindi"} <= fts.SUPPORTED_CONFIGS


def test_the_literal_and_the_frozenset_cannot_drift() -> None:
    """One declaration, two uses. The API schema needs the static type; SQL needs the set."""
    from typing import get_args

    assert set(get_args(fts.FtsConfigName)) == fts.SUPPORTED_CONFIGS
    assert fts.DEFAULT_CONFIG in fts.SUPPORTED_CONFIGS


@pytest.mark.parametrize("config", ["english", "simple"])
async def test_every_indexed_config_is_reachable_by_the_planner(
    db_session: AsyncSession, config: str
) -> None:
    """Migration 0019's job, re-asked after 0021 changed the expression underneath it.

    An expression index matches only the *exact* expression. `migrations/0004` created one, on
    `to_tsvector('english', content)`; 0019 added `simple` because a knowledge base switched to
    another configuration renders different SQL and would fall back to a sequential scan over
    every chunk — P0-1 reintroduced through the front door (docs/14 §5.4). 0021 then moved the
    expression to `coalesce(heading, '') || ' ' || content` (K2-6), which invalidates both of the
    original indexes in exactly the same way.

    This asks the **planner**, not `pg_indexes`, because the previous version of this test
    pattern-matched an index definition — and a definition string can agree with itself while
    disagreeing with what `fts_statement` renders, which is the only comparison that decides
    whether keyword retrieval touches an index. `enable_seqscan = off` removes "the table is
    small" as an explanation, so a Seq Scan here means *cannot use the index*.

    `scripts/explain_fts.py` covers the dimension a test cannot: a pooled asyncpg connection
    graduating from a custom plan to a generic one.
    """
    regconfig = fts.regconfig(config)
    predicate = fts.searchable(regconfig).op("@@")(fts.any_term_tsquery(regconfig, "refund policy"))
    sql = str(
        select(Chunk.id)
        .where(predicate)
        .compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )
    await db_session.execute(text("SET LOCAL enable_seqscan = off"))
    plan = "\n".join(
        str(row[0]) for row in (await db_session.execute(text(f"EXPLAIN {sql}"))).all()
    )
    assert f"ix_chunks_search_fts_{config}" in plan, plan


def test_the_searchable_expression_and_its_migration_cannot_drift() -> None:
    """`fts.SEARCHABLE_SQL` is what migration 0021 built the indexes from. One declaration.

    The migration cannot import from `app.rag.fts` — a migration has to keep working against the
    code as it was when the migration was written — so the string is duplicated on purpose and
    this test is the seam. Changing `searchable()` without a new migration is the P0-1 failure
    mode: every keyword query silently becomes a sequential scan over every chunk in the table.
    """
    path = Path(__file__).resolve().parents[1] / "migrations" / "versions" / _MIGRATION
    declared = next(
        line.split("=", 1)[1].strip().strip('"')
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.startswith("_SEARCHABLE =")
    )
    assert declared == fts.SEARCHABLE_SQL
    # And the helper really does render that expression, rather than the string being decoration.
    rendered = str(
        fts.searchable(fts.regconfig("english")).compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    assert "coalesce(chunks.heading, '')" in rendered.lower()
    assert "chunks.content" in rendered


async def test_every_supported_config_exists_on_this_postgres(db_session: AsyncSession) -> None:
    """The frozenset is a hardcoded copy of `pg_ts_config`, so check it against the server.

    A name in the list that Postgres does not have would raise `text search configuration
    "x" does not exist` at query time for whichever knowledge base selected it — i.e. it would
    fail for one client, in production, and nowhere else.
    """
    rows = (await db_session.execute(text("SELECT cfgname FROM pg_ts_config"))).scalars().all()
    missing = fts.SUPPORTED_CONFIGS - set(rows)
    assert not missing, f"not present on this server: {sorted(missing)}"
