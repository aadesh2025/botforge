#!/usr/bin/env python
"""Prove the FTS half of hybrid retrieval uses its GIN index (docs/14 §0, task P0-1).

    cd apps/api && ./.venv/Scripts/python.exe ../../scripts/explain_fts.py
    make explain-fts

**Why a script and not a test.** Whether Postgres uses an index is a property of the *planner*
on *real data*, not of the SQL string. A unit test can pin the rendered SQL (and
`tests/test_rag_fts.py` does); only `EXPLAIN` against a populated database can tell you the
plan. docs/14 §0 called this "plan-dependent — measure, do not assert", and this is the measure.

**It forces a generic plan on purpose.** A prepared statement's first ~5 executions get a
*custom* plan, where Postgres folds the parameter into a constant and the index matches anyway.
That is why the bug was invisible in dev. asyncpg prepares every statement and pools
connections, so a long-lived production connection graduates to the generic plan — which is the
plan this script reports. `enable_seqscan=off` removes the "table is too small to bother"
explanation, so a sequential scan in the output means *cannot use the index*, not *chose not
to*.

Exits **1** if the literal form does not reach `ix_chunks_content_fts`, so it can gate a PR.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

from sqlalchemy import select, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings
from app.models import Chunk
from app.rag import fts
from app.rag.fts import DEFAULT_CONFIG, normalize_config
from app.rag.retrieval import fts_statement

#: Set per configuration by migration 0021, over `fts.SEARCHABLE_SQL` (heading + content).
#: The pre-0021 name was `ix_chunks_content_fts`, over `content` alone.
_INDEX = "ix_chunks_search_fts_english"

# The control. This is what `func.to_tsvector("english", ...)` rendered before P0-1; a
# comparison with nothing to compare against proves nothing.
_PARAMETER_PREPARE = (
    "PREPARE bf_fts_param(regconfig, text) AS "
    "SELECT id FROM chunks WHERE to_tsvector($1, content) @@ plainto_tsquery($1, $2)"
)


def _inline(stmt: object) -> str:
    return str(
        stmt.compile(  # type: ignore[attr-defined]
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


def _match_only_sql(config: str, query: str) -> str:
    """The FTS predicate alone, built from the same `rag/fts` helpers production uses.

    **This is the P0-1 gate, and it deliberately drops the tenant filters.** With them in place
    the planner may legitimately prefer `ix_chunks_organization_id` — filtering to one org is
    very selective, so on a small table that is the *better* plan and says nothing about whether
    the expression index is usable. Stripping them isolates the only question P0-1 asks: can
    Postgres match this expression to `ix_chunks_content_fts` at all?
    """
    tsvector = fts.searchable(fts.regconfig(config))
    tsquery = fts.any_term_tsquery(fts.regconfig(config), query)
    return _inline(select(Chunk.id).where(tsvector.op("@@")(tsquery)))


def _real_query_sql(config: str, query: str) -> str:
    """The production statement itself, values inlined — informational, not the gate.

    Compiled from `retrieval.fts_statement()` rather than retyped, so this script cannot drift
    away from the query it claims to be explaining. It would have done exactly that the moment
    the tsquery changed from all-terms to any-term.
    """
    return _inline(fts_statement(uuid.uuid4(), [uuid.uuid4()], query, 20, config))


async def _plan(conn: object, sql: str, params: dict[str, object] | None = None) -> str:
    rows = await conn.execute(text(f"EXPLAIN {sql}"), params or {})  # type: ignore[attr-defined]
    return "\n".join(str(r[0]) for r in rows)


async def explain(config: str, query: str) -> int:
    engine = create_async_engine(settings.database_url)
    failures: list[str] = []
    async with engine.connect() as conn:
        count = (await conn.execute(text("SELECT count(*) FROM chunks"))).scalar_one()
        indexes = [
            r[0]
            for r in (
                await conn.execute(
                    text("SELECT indexname FROM pg_indexes WHERE tablename = 'chunks'")
                )
            ).all()
        ]
        print(f"\nchunks: {count} row(s)   config: {config}   query: {query!r}")
        if _INDEX not in indexes:
            print(f"\n!! {_INDEX} does not exist. Run `alembic upgrade head` first.\n")
            await engine.dispose()
            return 1

        # A small table is legitimately faster to scan; this removes that as an explanation so
        # the only remaining reason for a seq scan is "the expression does not match".
        await conn.execute(text("SET enable_seqscan = off"))
        await conn.execute(text("SET plan_cache_mode = force_generic_plan"))

        # ASCII only: a Windows console defaults to cp1252 and a box-drawing character raises
        # UnicodeEncodeError partway through, which loses the plan this script exists to print.
        # Same lesson as scripts/audit_kb_pii.py.
        match_plan = await _plan(conn, _match_only_sql(config, query))
        print("\n-- GATE: the FTS predicate alone, literal regconfig " + "-" * 26)
        print(match_plan)
        if _INDEX not in match_plan:
            failures.append(
                f"the literal form did NOT reach {_INDEX} - the expression no longer matches "
                "the index, so keyword retrieval is a sequential scan"
            )

        real_plan = await _plan(conn, _real_query_sql(config, query))
        print("\n-- for information: the full production statement " + "-" * 28)
        print(real_plan)
        if _INDEX not in real_plan:
            # Not a failure. `ix_chunks_organization_id` is often the better access path once
            # the tenant filter is applied, especially on a small table.
            print(
                f"\n(note) the planner chose another index for the full query. That is a data\n"
                f"       and selectivity decision, not an expression mismatch - the gate above\n"
                f"       is what says whether {_INDEX} is usable at all."
            )

        await conn.execute(text(_PARAMETER_PREPARE))
        # `EXECUTE` takes no driver-level parameters — asyncpg reports "the server expects 0
        # arguments". The values are inlined here, which is safe and beside the point: the
        # parameterisation being tested lives in the PREPARE above, and this is a local
        # operator script whose inputs come from argparse.
        param_plan = await _plan(
            conn, f"EXECUTE bf_fts_param('{config}', '{query.replace(chr(39), chr(39) * 2)}')"
        )
        print("\n-- bind-parameter regconfig (the pre-P0-1 shape, generic plan) " + "-" * 16)
        print(param_plan)
        if _INDEX in param_plan:
            # Not a failure: it would mean this Postgres does something newer than 16.14 did.
            # Worth printing loudly either way, because it would change the reason P0-1 exists.
            print(
                f"\n(!) The parameter form reached {_INDEX} on this server. That is not what "
                "PostgreSQL 16.14 does; re-read docs/14 §0 before trusting it."
            )

    await engine.dispose()
    if failures:
        print("\nFAIL: " + "\n      ".join(failures) + "\n")
        return 1
    print(f"\nOK: the keyword half of hybrid retrieval is served by {_INDEX}.\n")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--config", default=DEFAULT_CONFIG, help="text-search configuration")
    parser.add_argument("--query", default="refund policy", help="query text to plan")
    args = parser.parse_args()
    # Through the same allowlist the query path uses, so `--config` cannot introduce a name
    # that this script would then report as working.
    return asyncio.run(explain(normalize_config(args.config), args.query))


if __name__ == "__main__":
    raise SystemExit(main())
