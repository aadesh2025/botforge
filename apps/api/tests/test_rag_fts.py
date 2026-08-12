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


async def test_every_supported_config_exists_on_this_postgres(db_session: AsyncSession) -> None:
    """The frozenset is a hardcoded copy of `pg_ts_config`, so check it against the server.

    A name in the list that Postgres does not have would raise `text search configuration
    "x" does not exist` at query time for whichever knowledge base selected it — i.e. it would
    fail for one client, in production, and nowhere else.
    """
    rows = (await db_session.execute(text("SELECT cfgname FROM pg_ts_config"))).scalars().all()
    missing = fts.SUPPORTED_CONFIGS - set(rows)
    assert not missing, f"not present on this server: {sorted(missing)}"
