"""Token pricing and cost accounting (docs/06 §1)."""

from __future__ import annotations

from app.core.logging import get_logger
from app.llm import catalog
from app.llm.types import Usage

log = get_logger("llm.pricing")

# Free-first providers cost nothing. Derived from the catalog's `free` flag (+ the test stub)
# so adding a free-tier provider there doesn't leave it billing at an invented rate here.
FREE_PROVIDERS = {p.name for p in catalog.PROVIDERS if p.free} | {"fake"}

# (provider, model) -> (prompt micros / 1K tokens, completion micros / 1K tokens).
# 1 micro = $0.000001, so gpt-4o at $2.50/1M prompt = 2500 micros/1K.
# These are *overrides* consulted ahead of the catalog's own per-model rates; entries stay here
# for models no longer in the catalog, so an agent still pointed at one keeps costing what it
# always did rather than silently dropping to zero.
PRICING: dict[tuple[str, str], tuple[int, int]] = {
    ("openai", "gpt-4o"): (2500, 10000),
    ("openai", "gpt-4o-mini"): (150, 600),
    ("openai", "gpt-4.1-mini"): (400, 1600),
    ("anthropic", "claude-sonnet-5"): (3000, 15000),
    ("anthropic", "claude-haiku-4-5-20251001"): (800, 4000),
    ("anthropic", "claude-opus-4-8"): (15000, 75000),
}


def price_for(provider: str, model: str) -> tuple[int, int]:
    """Micros per 1K tokens for (provider, model), as (prompt, completion).

    A *model* rate outranks the provider's `free` flag, which is a default rather than a
    guarantee: OpenRouter is free-tier-first yet routes `anthropic/claude-sonnet-4.5` to a
    billed upstream. Checking the free flag first (as this did) made every model on such a
    provider report $0, so switching an agent onto a paid model showed no cost change at
    all. Groq and Gemini's free models publish no rate, so they still come back (0, 0).
    """
    override = PRICING.get((provider, model))
    if override is not None:
        return override
    spec = catalog.find_model(provider, model)
    if spec is not None and spec.prompt_micros is not None and spec.completion_micros is not None:
        return (spec.prompt_micros, spec.completion_micros)
    return (0, 0)


def compute_cost_micros(provider: str, model: str, usage: Usage) -> int:
    prompt_rate, completion_rate = price_for(provider, model)
    if (prompt_rate, completion_rate) == (0, 0) and provider not in FREE_PROVIDERS:
        # A paid model reporting $0 is a wrong number in the client's analytics, not a free
        # turn. Say so rather than letting it read as "this costs nothing" (docs/PROGRESS.md
        # has two entries about exactly this class of silence).
        log.warning("pricing_unknown", provider=provider, model=model)
    micros = usage.prompt_tokens * prompt_rate / 1000 + usage.completion_tokens * completion_rate / 1000
    return round(micros)
