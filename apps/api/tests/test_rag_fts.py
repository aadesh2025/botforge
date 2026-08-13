"""P0-1 — the FTS regconfig must render as a literal, or the GIN index cannot match.

`scripts/explain_fts.py` proves the *plan* against a populated database; this file pins the
*SQL*, so a future refactor back to `func.to_tsvector("english", ...)` fails in CI instead of
quietly returning the whole `chunks` table to a sequential scan on a long-lived connection.

See `app/rag/fts.py` for the measured EXPLAIN and why a custom plan hides this in dev.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from app.rag import fts
from app.rag.retrieval import fts_statement


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


async def test_a_non_english_config_has_an_index_to_use(db_session: AsyncSession) -> None:
    """Migration 0019's real job.

    `migrations/0004` created ONE expression index, on `to_tsvector('english', content)`. An
    expression index matches only the exact expression, so a knowledge base switched to another
    configuration renders different SQL and falls back to a sequential scan over every chunk —
    P0-1 reintroduced through the front door. docs/14 §5.4 warns about precisely this.
    """
    rows = (
        await db_session.execute(
            text("SELECT indexdef FROM pg_indexes WHERE tablename = 'chunks'")
        )
    ).scalars().all()
    defs = " ".join(rows)
    assert "to_tsvector('english'::regconfig, content)" in defs
    assert "to_tsvector('simple'::regconfig, content)" in defs


async def test_every_supported_config_exists_on_this_postgres(db_session: AsyncSession) -> None:
    """The frozenset is a hardcoded copy of `pg_ts_config`, so check it against the server.

    A name in the list that Postgres does not have would raise `text search configuration
    "x" does not exist` at query time for whichever knowledge base selected it — i.e. it would
    fail for one client, in production, and nowhere else.
    """
    rows = (await db_session.execute(text("SELECT cfgname FROM pg_ts_config"))).scalars().all()
    missing = fts.SUPPORTED_CONFIGS - set(rows)
    assert not missing, f"not present on this server: {sorted(missing)}"
