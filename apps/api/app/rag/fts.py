"""Postgres full-text search configuration for the keyword half of hybrid retrieval.

**Why this module exists at all: an expression index only matches a literal.**

`migrations/0004` builds the GIN index on ``to_tsvector('english', content)`` — a *constant*
regconfig. SQLAlchemy's ``func.to_tsvector("english", Chunk.content)`` renders the config as a
**bind parameter** instead, and the planner can only use an expression index when it can prove
the two expressions are identical. A ``Param`` node never matches a ``Const`` node.

Measured on the live database (PostgreSQL 16.14), not asserted — this is the `EXPLAIN` docs/14
§0 asked for, and it settles the "plan-dependent" question in both directions::

    -- literal:  uses the index
    Bitmap Index Scan on ix_chunks_content_fts

    -- parameter, force_generic_plan:  cannot use it, even with enable_seqscan=off
    Seq Scan on chunks  (cost=10000000000.00..10000000012.15)
      Filter: (to_tsvector($1, content) @@ plainto_tsquery($1, $2))

A *custom* plan folds the parameter and does match, which is why this never showed up in dev:
the first ~5 executions of a prepared statement look fine. asyncpg prepares every statement and
pools connections, so a long-lived production connection graduates to the generic plan and
starts sequentially scanning every chunk in the table. Hence: render the config as a literal.

**The interpolation is safe because the value is allowlisted, not escaped.** `fts_config`
becomes operator-settable per knowledge base, so it is untrusted input reaching a position no
bind parameter can occupy. `normalize_config()` maps anything outside `SUPPORTED_CONFIGS` back
to the default, so only a name from the frozenset below can ever reach the f-string.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import literal_column
from sqlalchemy.sql.elements import ColumnElement

from app.core.logging import get_logger

log = get_logger("rag.fts")

DEFAULT_CONFIG = "english"

#: The text-search configurations PostgreSQL 16 ships (``select cfgname from pg_ts_config``),
#: read off the running database rather than a changelog.
#:
#: **docs/13 R4b and docs/14 §5.4 are wrong to say Postgres ships no Tamil or Hindi dictionary.**
#: PostgreSQL 16 added both, and `tamil` really stems — ``கொள்கைகள்`` → ``கொள்கை``,
#: ``திரும்பப்`` → ``திரும்`` — it is not a `simple` alias. In a market where Tamil is a first
#: language (docs/11 §9.2a) that is the difference between the keyword half of hybrid retrieval
#: being degraded and it being genuinely useful, so the correction is worth more than the fix.
#: `simple` (tokenise, never stem) stays the right answer for a language with no entry here.
SUPPORTED_CONFIGS: frozenset[str] = frozenset(
    {
        "simple",
        "arabic",
        "armenian",
        "basque",
        "catalan",
        "danish",
        "dutch",
        "english",
        "finnish",
        "french",
        "german",
        "greek",
        "hindi",
        "hungarian",
        "indonesian",
        "irish",
        "italian",
        "lithuanian",
        "nepali",
        "norwegian",
        "portuguese",
        "romanian",
        "russian",
        "serbian",
        "spanish",
        "swedish",
        "tamil",
        "turkish",
        "yiddish",
    }
)


def normalize_config(name: str | None) -> str:
    """Coerce a stored `fts_config` to something Postgres will accept.

    Deliberately forgiving on the *read* path and strict on the write path (the API schema
    rejects an unknown name outright). A knowledge base holding a config this Postgres does not
    have — restored from a newer server, or a dictionary that was dropped — must still answer
    queries in a degraded way rather than raise `text search configuration does not exist` at
    every visitor. The fallback is logged, because a KB silently searching in the wrong language
    looks exactly like a KB whose content is simply hard to retrieve.
    """
    config = (name or "").strip().lower()
    if not config:
        return DEFAULT_CONFIG
    if config not in SUPPORTED_CONFIGS:
        log.warning(
            "fts_config_unsupported",
            requested=config[:64],
            using=DEFAULT_CONFIG,
            impact="keyword retrieval is running in the wrong language for this knowledge base",
        )
        return DEFAULT_CONFIG
    return config


def regconfig(name: str | None = None) -> ColumnElement[Any]:
    """The regconfig as a SQL **literal**, so the expression index can match it.

    Never build this with a bind parameter — see the module docstring for the `EXPLAIN` that
    shows what happens when you do.
    """
    config = normalize_config(name)
    # Safe: `config` is a member of SUPPORTED_CONFIGS, which contains only `[a-z]+` names.
    return literal_column(f"'{config}'::regconfig")
