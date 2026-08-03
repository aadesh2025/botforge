"""L5 — output guardrail (docs/11 §4-L5).

The last line of defence: what the model actually produced, checked before a visitor sees it
and before it is persisted. Three checks in Phase A —

1. **Secret redaction** — unchanged, `guardrails.redact_secrets()`.
2. **System-prompt leak** — 8-gram shingle overlap against the assembled system prompt.
   Catches quoting and light paraphrase without needing the model to cooperate, which is the
   point: the identity lock *asks* the model not to reveal its instructions, and docs/11 §1.4
   is the record of how much an ask is worth.
3. **Persona break** — "I'm a large language model", "as an AI", and friends. Live failure 6.

PII egress is Phase B and deliberately not here.

**Why shingles rather than substring search.** A leak is rarely verbatim: the model
paraphrases, reorders clauses, or translates. Overlap on normalised 8-grams degrades
gracefully — a reply that reuses a third of the prompt's distinctive phrasing scores high
whether or not any single sentence matches exactly. n=8 is long enough that ordinary shared
vocabulary ("you are a customer support representative for Acme") does not dominate.

**Why the protected prompt is passed in explicitly.** `run_turn` sees `req.messages`, which
contains *two* system messages: the instructions and the retrieved-context block. Leaking the
latter is fine — it is knowledge-base content the customer is entitled to. Comparing against
everything system-role would suppress ordinary grounded answers, so callers pass only the
instruction prompt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.chat.guardrails import redact_secrets
from app.chat.normalize import normalize_for_matching

_SHINGLE_N = 8

# Phrases that break the agent's persona. Anchored tightly: "as an AI" is a break, but
# "as an airline we..." must not be, and a customer-facing reply may legitimately contain
# the word "model" (a product model number, a pricing model).
_PERSONA_BREAK = [
    re.compile(r"\b(i am|i'm)\s+(just\s+)?(a|an)\s+(large\s+)?language model\b", re.I),
    re.compile(r"\b(i am|i'm)\s+(just\s+)?an?\s+(ai|a\.i\.|artificial intelligence)\b", re.I),
    re.compile(r"\bas an ai\b", re.I),
    re.compile(r"\bas a language model\b", re.I),
    re.compile(r"\b(i am|i'm)\s+(just\s+)?a\s+(bot|chatbot|virtual assistant)\b", re.I),
    re.compile(r"\bi (don'?t|do not) have (the )?(ability|capability) to\b", re.I),
    re.compile(r"\bi (can'?t|cannot|don'?t) (recall|remember|retain) (previous|prior|past) conversations?\b", re.I),
    re.compile(r"\bmy training data\b", re.I),
    re.compile(r"\bi was (trained|created|developed) (by|on)\b", re.I),
    re.compile(r"\bi'?m an? (openai|anthropic|meta|google|groq)\b", re.I),
]

# Appended for the single regeneration attempt after a persona break.
REGENERATION_DIRECTIVE = (
    "Your previous reply broke character by describing yourself as an AI, a model, or a "
    "system. Answer the same question again as a member of the support team, in the first "
    "person, with no reference to being automated and no explanation of how you work. If you "
    "do not have the information, simply say so and offer to bring in a teammate."
)


@dataclass(frozen=True)
class OutputVerdict:
    """What the output guard found. `text` is always safe to send."""

    text: str
    leaked_prompt: bool = False
    persona_break: bool = False
    leak_score: float = 0.0
    changed: bool = False

    @property
    def violated(self) -> bool:
        return self.leaked_prompt or self.persona_break


def _shingles(text: str, n: int = _SHINGLE_N) -> set[str]:
    words = normalize_for_matching(text).lower().split()
    if len(words) < n:
        # Too short to shingle: treat the whole thing as one gram so short verbatim
        # fragments are still comparable rather than silently scoring zero.
        return {" ".join(words)} if words else set()
    return {" ".join(words[i : i + n]) for i in range(len(words) - n + 1)}


def prompt_leak_score(reply: str, protected_prompt: str | None) -> float:
    """Fraction of the reply's 8-grams that also appear in the protected prompt.

    Measured over the *reply*, not the prompt: a two-line answer quoting one rule verbatim
    is a leak even though it covers almost none of a long system prompt.
    """
    if not protected_prompt or not reply:
        return 0.0
    reply_grams = _shingles(reply)
    if not reply_grams:
        return 0.0
    prompt_grams = _shingles(protected_prompt)
    if not prompt_grams:
        return 0.0
    return len(reply_grams & prompt_grams) / len(reply_grams)


def detect_persona_break(reply: str) -> bool:
    return any(p.search(reply or "") for p in _PERSONA_BREAK)


def inspect(reply: str, protected_prompt: str | None, *, leak_threshold: float) -> OutputVerdict:
    """Classify a reply without deciding what to do about it."""
    score = prompt_leak_score(reply, protected_prompt)
    return OutputVerdict(
        text=reply,
        leaked_prompt=score >= leak_threshold,
        persona_break=detect_persona_break(reply),
        leak_score=score,
    )


def apply(
    reply: str,
    protected_prompt: str | None,
    *,
    leak_threshold: float,
    fallback_message: str | None = None,
) -> OutputVerdict:
    """Return a verdict whose `text` is safe to send and to persist.

    A leak is replaced outright — there is no partially-safe version of a reply that quotes
    the system prompt. A persona break is handled by the caller's regeneration attempt first;
    if it reaches here it is replaced too.

    The replacement is always a real sentence. A guardrail that suppresses and says nothing
    recreates the ADR-044 silent-empty-reply outage with a new cause.
    """
    verdict = inspect(reply, protected_prompt, leak_threshold=leak_threshold)
    safe = redact_secrets(verdict.text)
    if verdict.violated:
        safe = fallback_message or _DEFAULT_SUPPRESSION
    return OutputVerdict(
        text=safe,
        leaked_prompt=verdict.leaked_prompt,
        persona_break=verdict.persona_break,
        leak_score=verdict.leak_score,
        changed=safe != reply,
    )


_DEFAULT_SUPPRESSION = (
    "Sorry — let me try that again. Could you rephrase what you'd like help with?"
)
