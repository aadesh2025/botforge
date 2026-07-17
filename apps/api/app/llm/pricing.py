"""Token pricing and cost accounting (docs/06 §1)."""

from __future__ import annotations

from app.llm.types import Usage

# Free-first providers cost nothing.
FREE_PROVIDERS = {"groq", "gemini", "ollama", "openrouter", "fake", "custom"}

# (provider, model) -> (prompt micros / 1K tokens, completion micros / 1K tokens).
# 1 micro = $0.000001, so gpt-4o at $2.50/1M prompt = 2500 micros/1K.
PRICING: dict[tuple[str, str], tuple[int, int]] = {
    ("openai", "gpt-4o"): (2500, 10000),
    ("openai", "gpt-4o-mini"): (150, 600),
    ("openai", "gpt-4.1-mini"): (400, 1600),
    ("anthropic", "claude-sonnet-5"): (3000, 15000),
    ("anthropic", "claude-haiku-4-5-20251001"): (800, 4000),
    ("anthropic", "claude-opus-4-8"): (15000, 75000),
}


def price_for(provider: str, model: str) -> tuple[int, int]:
    if provider in FREE_PROVIDERS:
        return (0, 0)
    return PRICING.get((provider, model), (0, 0))


def compute_cost_micros(provider: str, model: str, usage: Usage) -> int:
    prompt_rate, completion_rate = price_for(provider, model)
    micros = usage.prompt_tokens * prompt_rate / 1000 + usage.completion_tokens * completion_rate / 1000
    return round(micros)
