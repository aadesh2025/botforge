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

from typing import Any, Literal, get_args

from sqlalchemy import Text, cast, func, literal_column
from sqlalchemy.dialects.postgresql import TSQUERY
from sqlalchemy.sql.elements import ColumnElement

from app.core.logging import get_logger

log = get_logger("rag.fts")

#: The text-search configurations PostgreSQL 16 ships (``select cfgname from pg_ts_config``),
#: read off the running database rather than a changelog.
#:
#: **docs/13 R4b and docs/14 §5.4 are wrong to say Postgres ships no Tamil or Hindi dictionary.**
#: PostgreSQL 16 added both, and `tamil` really stems — ``கொள்கைகள்`` → ``கொள்கை``,
#: ``திரும்பப்`` → ``திரும்`` — it is not a `simple` alias. In a market where Tamil is a first
#: language (docs/11 §9.2a) that is the difference between the keyword half of hybrid retrieval
#: being degraded and it being genuinely useful, so the correction is worth more than the fix.
#: `simple` (tokenise, never stem) stays the right answer for a language with no entry here.
#:
#: Declared as a `Literal` and the frozenset derived from it, not the other way round: the API
#: schema needs a static type (mypy rejects `Literal[*sorted(some_set)]`, and a dynamic one
#: produces no enum in the OpenAPI document), while the query path needs cheap membership
#: checks. One declaration, both uses, nothing to drift.
FtsConfigName = Literal[
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
]

SUPPORTED_CONFIGS: frozenset[str] = frozenset(get_args(FtsConfigName))

DEFAULT_CONFIG: FtsConfigName = "english"


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


#: The SQL text the keyword half searches, as a single source of truth shared by the query and
#: by the migration that indexes it. **An expression index matches only the exact expression**,
#: so if these two ever diverge by one character the index silently stops being used and
#: keyword retrieval becomes a sequential scan — P0-1, reintroduced. `scripts/explain_fts.py`
#: is the thing that would catch it.
#:
#: `heading || ' ' || content` rather than `content` alone because of the K2-5 measurement
#: (ADR-065/ADR-067): the structural chunker moves a chunk's heading path into the *embedding*
#: input, which improved dense retrieval (+0.0104 NDCG@10) and took the heading out of the text
#: FTS searches (-0.0206), leaving the fused result net negative. This is the lexical twin of
#: `TextChunk.embed_text`: the heading informs the search without being pasted into `content`,
#: which stays the clean citation text a visitor is shown.
#:
#: `coalesce(...)` is load-bearing: `NULL || ' ' || content` is NULL in SQL, so without it every
#: legacy chunk — which has no heading — would index as nothing at all.
SEARCHABLE_SQL = "coalesce(heading, '') || ' ' || content"


def searchable(config: ColumnElement[Any]) -> ColumnElement[Any]:
    """`to_tsvector` over heading + content. Must render identically to `SEARCHABLE_SQL`."""
    from app.models import Chunk

    return func.to_tsvector(config, func.coalesce(Chunk.heading, "") + " " + Chunk.content)


def any_term_tsquery(config: ColumnElement[Any], query: str | ColumnElement[Any]) -> ColumnElement[Any]:
    """A tsquery matching **any** of the query's terms, ranked — not all of them.

    `plainto_tsquery` joins every lexeme with `&`, so it only matches a chunk containing all of
    them. That is right for a search box and wrong for a support bot, because a customer types a
    sentence::

        plainto_tsquery('english', "ordered a kurta to delhi last week and it doesn't
                                    suit me, how long have i got")
        -> 'order' & 'kurta' & 'delhi' & 'last' & 'week' & 'doesnt' & 'suit' & 'long' & 'got'

    No chunk contains all nine, so the keyword half returned nothing. Measured on the frozen
    eval corpus it scored **NDCG@10 0.0278 — one query in thirty-six** — and because RRF then
    had a single list to fuse, `hybrid` came out byte-identical to `dense`. The hybrid retrieval
    this product advertises was dense-only in production.

    ORing the terms turns the keyword half into what it was supposed to be: a recall stage whose
    *ranking* discriminates. `ts_rank` already accounts for how many query terms a chunk matches
    and how often, so a chunk hitting six terms outranks one hitting two, and RRF fuses two
    genuinely independent orderings.

    **Why `replace(...::text, '&', '|')` and not something tidier.** `plainto_tsquery` has
    already done the work that matters — stemming under the right dictionary, stopword removal,
    and correct quoting of each lexeme — and its output is only ever `&`-joined lexemes (phrase
    operators come from `phraseto_tsquery`, which we do not use). Rebuilding the query from
    `tsvector_to_array` would have to re-quote lexemes by hand and get it wrong on the first
    apostrophe. Checked against the cases that would break a naive substitution:

        'R&D budget & cost' -> 'r' | 'd' | 'budget' | 'cost'   (& is a separator, never a lexeme)
        'the and of'        -> <empty>                          (matches nothing, no error)
        ''                  -> <empty>

    ADR-062.
    """
    plain = func.plainto_tsquery(config, query)
    return cast(func.replace(cast(plain, Text), "&", "|"), TSQUERY)
