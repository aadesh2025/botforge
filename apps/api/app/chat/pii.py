"""PII detection shared by output redaction (docs/11 §4-L5) and ingest scanning (§6).

One module so "what counts as a phone number" has a single answer. The output guard uses it to
stop PII leaving in a reply; the RAG ingest pipeline uses it to flag documents that carry PII
into the retrieval corpus. Those are the two halves of the live failure this exists for: asked
*"can i get your number or gmail"*, the agent returned the founder's personal email and mobile.
The model was not hallucinating — it retrieved them correctly from a knowledge base that should
never have held them.

**Phone numbers use `phonenumbers` (Google's libphonenumber), not a regex** — ADR-053. The
leaked number was an Indian mobile, and:

- a US-centric pattern misses `+91 93453 27506` entirely;
- a permissive digit-run pattern redacts order numbers, invoice totals and dates out of
  ordinary replies, which breaks the product to fix a leak.

libphonenumber validates against each country's real numbering plan, so `+91 93453 27506`
matches and `9345327506123` does not.

**A bare digit run is still ambiguous**, because a valid Indian mobile and a 10-digit order id
are the same string. So a match additionally has to *look* like a phone: an explicit `+`,
internal separators, or a phone-ish word nearby. `test_pii.py` pins both directions.

Nothing here decides policy. `find_pii()` reports; the caller decides what to redact, and the
allowlist lives with the caller because "our own support line" is org-level configuration.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from phonenumbers import Leniency, PhoneNumberMatcher

PiiKind = Literal["email", "phone", "address"]

# Deliberately not the full RFC 5322 monster: this needs to catch what a model writes into a
# sentence, and an over-clever pattern costs more in false positives than it gains.
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")

# Words that make a digit run a phone number rather than a reference number.
_PHONE_CONTEXT = re.compile(
    r"\b(call|phone|mobile|cell|whats\s?app|telephone|tel|contact|reach|dial|ring|"
    r"number|hotline|helpline|landline)\b",
    re.I,
)
_PHONE_SEPARATORS = re.compile(r"[ \-.()]")

# Street addresses, best effort. Kept narrow and **flag-only by default** (`redact_addresses`
# is off) because the precision is nowhere near the other two: "12 Month Plan" and "24 Hour
# Support" both look like a house number followed by a road word.
_ADDRESS = re.compile(
    r"\b\d{1,5}\s+([A-Z][A-Za-z]{2,}\s+){1,3}"
    r"(street|st|road|rd|avenue|ave|lane|ln|boulevard|blvd|drive|dr|nagar|colony|marg|"
    r"sector|block)\b",
    re.I,
)


@dataclass(frozen=True)
class PiiMatch:
    kind: PiiKind
    value: str
    start: int
    end: int


def _normalize_contact(value: str) -> str:
    """Comparison form for the allowlist: an operator writes a number however they like."""
    v = (value or "").strip().lower()
    if "@" in v:
        return v
    digits = re.sub(r"[^\d+]", "", v)
    # Compare on the last 10 digits so "+91 93453 27506", "093453 27506" and "9345327506"
    # all resolve to the same contact.
    tail = re.sub(r"\D", "", digits)
    return tail[-10:] if len(tail) >= 10 else (digits or v)


def build_allowlist(entries: list[str] | None) -> set[str]:
    """Normalised set of contacts an agent may share freely."""
    return {_normalize_contact(e) for e in (entries or []) if str(e).strip()}


def is_allowlisted(value: str, allowlist: set[str]) -> bool:
    return _normalize_contact(value) in allowlist


def _phone_matches(text: str, regions: list[str]) -> list[PiiMatch]:
    seen: dict[tuple[int, int], PiiMatch] = {}
    # `None` finds numbers written with an explicit +country code in any country; each named
    # region additionally finds locally-formatted numbers for that country.
    for region in [None, *regions]:
        try:
            matcher = PhoneNumberMatcher(text, region, leniency=Leniency.VALID)
            for m in matcher:
                raw = text[m.start : m.end]
                explicit = raw.lstrip().startswith("+")
                separated = bool(_PHONE_SEPARATORS.search(raw.strip()))
                window = text[max(0, m.start - 30) : m.start]
                contextual = bool(_PHONE_CONTEXT.search(window))
                if not (explicit or separated or contextual):
                    # A bare digit run with no formatting and no phone word: far more likely
                    # an order or invoice reference, and redacting those breaks real answers.
                    continue
                seen[(m.start, m.end)] = PiiMatch("phone", raw, m.start, m.end)
        except Exception:  # a bad region string must never break a reply
            continue
    return list(seen.values())


def find_pii(
    text: str,
    *,
    regions: list[str] | None = None,
    include_addresses: bool = True,
) -> list[PiiMatch]:
    """Every PII span in `text`, ordered by position. Reports; does not redact."""
    text = text or ""
    if not text.strip():
        return []
    found: list[PiiMatch] = [
        PiiMatch("email", m.group(0), m.start(), m.end()) for m in _EMAIL.finditer(text)
    ]
    email_spans = [(m.start, m.end) for m in found]
    for pm in _phone_matches(text, regions or []):
        # A phone-looking run inside an email address is part of the address, not a number.
        if any(s <= pm.start < e for s, e in email_spans):
            continue
        found.append(pm)
    if include_addresses:
        found.extend(
            PiiMatch("address", m.group(0), m.start(), m.end()) for m in _ADDRESS.finditer(text)
        )
    return sorted(found, key=lambda m: m.start)


def summarize(matches: list[PiiMatch]) -> dict[str, int]:
    """`{kind: count}` — the shape stored on a document and printed by the audit script.

    Counts only. The value itself is never stored or reported: a PII report that echoes the
    PII is the same leak in a different place.
    """
    out: dict[str, int] = {}
    for m in matches:
        out[m.kind] = out.get(m.kind, 0) + 1
    return out
