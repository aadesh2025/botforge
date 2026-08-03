"""L0 — input normalisation for guardrail *matching* (docs/11 §4-L0).

Attackers defeat regex with encoding, not cleverness: `ign​ore previous instructions`
and `іgnore` (Cyrillic і) both read as English to a human and to the model, but neither
matches a pattern written in ASCII. So every guardrail matches against a normalised copy
in addition to the raw text.

> **The text sent to the model and stored in the database stays exactly what the customer
> typed.** Normalisation exists to feed the matchers a second (and third) candidate string,
> never to rewrite someone's words. `screen_user_message()` returns a verdict; it does not
> return a cleaned message, and nothing here is wired into persistence.

The decoders are deliberately shallow — one level, obvious encodings only. A base64 blob is
worth a second look because it is a known evasion; recursively unwrapping arbitrary encodings
is how a normaliser becomes its own denial-of-service vector (LLM10).
"""

from __future__ import annotations

import base64
import binascii
import codecs
import re
import unicodedata
from urllib.parse import unquote

# Zero-width and bidirectional-control characters. These render as nothing, so they split a
# keyword for a regex while leaving it perfectly readable to a human and to the model.
_INVISIBLE = dict.fromkeys(
    [
        0x200B,  # zero-width space
        0x200C,  # zero-width non-joiner
        0x200D,  # zero-width joiner
        0x2060,  # word joiner
        0xFEFF,  # zero-width no-break space / BOM
        0x00AD,  # soft hyphen
        0x180E,  # Mongolian vowel separator
        0x202A,  # LRE  ┐
        0x202B,  # RLE  │ bidi overrides — used to visually reorder an attack payload
        0x202C,  # PDF  │
        0x202D,  # LRO  │
        0x202E,  # RLO  ┘
        0x2066,  # LRI
        0x2067,  # RLI
        0x2068,  # FSI
        0x2069,  # PDI
    ]
)

# Confusables that survive NFKC (which normalises compatibility forms, not cross-script
# lookalikes). Cyrillic and Greek cover the overwhelming majority of homoglyph attacks
# because their lowercase letters are pixel-identical to Latin in most fonts.
_HOMOGLYPHS = str.maketrans(
    {
        "а": "a", "е": "e", "о": "o", "р": "p", "с": "c",
        "у": "y", "х": "x", "і": "i", "ј": "j", "һ": "h",
        "А": "A", "Е": "E", "О": "O", "Р": "P", "С": "C",
        "Т": "T", "Х": "X", "М": "M", "Н": "H", "К": "K",
        "В": "B", "І": "I",
        "ο": "o", "α": "a", "ε": "e", "ρ": "p", "υ": "u",
        "ν": "v", "χ": "x", "Ι": "I", "Ο": "O", "Α": "A",
        "Β": "B", "Ε": "E", "Η": "H", "Κ": "K", "Μ": "M",
        "Ν": "N", "Ρ": "P", "Τ": "T", "Χ": "X", "Ζ": "Z",
    }
)

_WHITESPACE_RUN = re.compile(r"\s+")
# Base64 has to be long enough that ordinary words can't trip it. 40 chars is ~30 bytes of
# payload — comfortably above anything a customer types by accident.
_B64_BLOB = re.compile(r"[A-Za-z0-9+/]{40,}={0,2}")
_PERCENT_ENCODED = re.compile(r"%[0-9A-Fa-f]{2}")


def strip_invisible(text: str) -> str:
    """Remove zero-width and bidi-control characters."""
    return (text or "").translate(_INVISIBLE)


def fold_homoglyphs(text: str) -> str:
    """Fold Cyrillic/Greek lookalikes onto their Latin equivalents."""
    return (text or "").translate(_HOMOGLYPHS)


def normalize_for_matching(text: str, *, max_chars: int | None = None) -> str:
    """The canonical form guardrail patterns are matched against.

    NFKC → strip invisibles → fold homoglyphs → drop control characters → collapse
    whitespace → truncate. Order matters: folding before NFKC would miss compatibility
    forms, and collapsing whitespace before stripping invisibles would leave `a​ b`
    as two words.
    """
    out = unicodedata.normalize("NFKC", text or "")
    out = strip_invisible(out)
    out = fold_homoglyphs(out)
    # Keep \n and \t — they carry structure a delimiter-escape attempt relies on.
    out = "".join(ch for ch in out if ch in "\n\t" or not unicodedata.category(ch).startswith("C"))
    out = _WHITESPACE_RUN.sub(" ", out).strip()
    if max_chars is not None and max_chars > 0:
        out = out[:max_chars]
    return out


def _try_base64(text: str) -> list[str]:
    found: list[str] = []
    for blob in _B64_BLOB.findall(text)[:3]:  # bounded: 3 blobs is generous for a real message
        padded = blob + "=" * (-len(blob) % 4)
        try:
            decoded = base64.b64decode(padded, validate=True).decode("utf-8", errors="strict")
        except (binascii.Error, ValueError, UnicodeDecodeError):
            continue
        if decoded.strip():
            found.append(decoded)
    return found


def decoded_candidates(text: str) -> list[str]:
    """Extra strings to scan alongside the original — one decoding level, never substituted.

    A hit on any candidate is treated as a hit on the message. False positives here are
    cheap (a decode has to produce readable text *and* match an injection pattern), and the
    alternative is that `base64("ignore all previous instructions")` sails through.
    """
    text = text or ""
    out: list[str] = []
    out.extend(_try_base64(text))
    if _PERCENT_ENCODED.search(text):
        try:
            unquoted = unquote(text, errors="strict")
        except (UnicodeDecodeError, ValueError):
            unquoted = ""
        if unquoted and unquoted != text:
            out.append(unquoted)
    # ROT13 is trivial and still shows up in jailbreak kits. Only worth scanning when the
    # text is mostly alphabetic, so we don't rot13 a URL or a code snippet for nothing.
    letters = [c for c in text if c.isalpha()]
    if len(letters) >= 12:
        try:
            out.append(codecs.decode(text, "rot_13"))
        except (UnicodeDecodeError, LookupError, ValueError):
            pass
    return [c for c in out if c.strip()]


# Character-spacing evasion: "I g n o r e   a l l   p r e v i o u s". Same class as the
# zero-width trick, but it uses a character the normaliser legitimately keeps, so stripping is
# not an option — the collapsed form is emitted as an extra candidate instead.
#
# Both thresholds exist to protect precision. A span must be long *and* mostly single letters
# before anything collapses, which is what keeps "I need a A A battery" (5 tokens) and
# "my order id is A B 1 2 9 9" (10 tokens, 6 single) out of it.
_SPACED_MIN_TOKENS = 12
_SPACED_MIN_RATIO = 0.6
_TOKEN_SPLIT = re.compile(r"(\s+)")


def despaced_forms(text: str) -> list[str]:
    """Collapsed readings of a message written with letters spaced apart.

    Returns up to two strings, or nothing when the text does not look spaced out:

    - **gap-aware** — single spaces *between single characters* are treated as intra-word and
      removed, while wider gaps stay word boundaries. `"I g n o r e   a l l   p r e v i o u s"`
      becomes `"ignore all previous"`, which the existing L1 patterns match unchanged.
    - **fully collapsed** — every space removed, for the degenerate case where the attacker
      used one space everywhere and word boundaries are unrecoverable. Only useful against
      whitespace-relaxed patterns, which is how `screen_user_message()` uses it.
    """
    stripped = strip_invisible(unicodedata.normalize("NFKC", text or ""))
    parts = _TOKEN_SPLIT.split(stripped)
    tokens = [t for t in parts[0::2] if t]
    gaps = parts[1::2]
    if len(tokens) < _SPACED_MIN_TOKENS:
        return []
    singles = sum(1 for t in tokens if len(t) == 1)
    if singles / len(tokens) < _SPACED_MIN_RATIO:
        return []

    pieces: list[str] = []
    raw_tokens = parts[0::2]
    for i, tok in enumerate(raw_tokens):
        if not tok:
            continue
        pieces.append(tok)
        nxt = next((t for t in raw_tokens[i + 1 :] if t), None)
        if nxt is None:
            break
        gap = gaps[i] if i < len(gaps) else " "
        # Join only when a *single* space sits between two *single* characters. Anything
        # wider, or either side being a real word, stays a boundary.
        joined = len(gap) == 1 and len(tok) == 1 and len(nxt) == 1
        pieces.append("" if joined else " ")

    gap_aware = _WHITESPACE_RUN.sub(" ", "".join(pieces)).strip()
    collapsed = "".join(tokens)
    out = [gap_aware]
    if collapsed != gap_aware:
        out.append(collapsed)
    return [o for o in out if o]


def matching_candidates(text: str, *, max_chars: int | None = None) -> list[str]:
    """Every string a guardrail should test: raw, normalised, and shallow-decoded forms."""
    raw = text or ""
    candidates = [raw, normalize_for_matching(raw, max_chars=max_chars)]
    for decoded in decoded_candidates(raw):
        candidates.append(normalize_for_matching(decoded, max_chars=max_chars))
    for despaced in despaced_forms(raw):
        candidates.append(normalize_for_matching(despaced, max_chars=max_chars))
    # Order-preserving dedupe: patterns run once per distinct string.
    seen: set[str] = set()
    unique: list[str] = []
    for c in candidates:
        if c and c not in seen:
            seen.add(c)
            unique.append(c)
    return unique
