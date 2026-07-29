"""Finding contact details in a message: a cheap regex gate, then a small LLM.

The gate matters. Most messages contain no contact information at all, and running an LLM
over every inbound turn to discover that would cost real money for nothing. Email and phone
both have reliable shapes, so a regex answers "is there anything here?" for free; the model
only runs when there is.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AppError
from app.core.logging import get_logger
from app.llm.base import ChatProvider
from app.llm.fake import FakeChatProvider
from app.llm.registry import get_chat_provider
from app.llm.types import ChatRequest, Message

log = get_logger("crm.extract")

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]{2,}")
#: Deliberately loose — 7+ digits with common separators. Precision comes from the LLM pass
#: and from normalisation; a missed number is worse than a candidate we later discard.
_PHONE_RE = re.compile(r"(?:\+?\d[\d\s().-]{6,}\d)")
_DIGITS_RE = re.compile(r"\d")

_SYSTEM = (
    "You extract contact details from a single customer chat message. Return ONLY a JSON "
    "object with keys name, email, phone. Use null for anything the message does not state. "
    "Never invent or guess a name — only use one the customer actually gives. Copy the email "
    "and phone exactly as written."
)


@dataclass
class ContactHints:
    """What the cheap pass found. `any()` is the gate for the expensive pass."""

    email: str | None = None
    phone: str | None = None

    def any(self) -> bool:
        return bool(self.email or self.phone)


@dataclass
class ExtractedContact:
    name: str | None = None
    email: str | None = None
    phone: str | None = None

    def any(self) -> bool:
        return bool(self.name or self.email or self.phone)


def normalize_email(value: str | None) -> str | None:
    """Lowercased and trimmed, so lookups are exact matches rather than near-misses."""
    if not value:
        return None
    cleaned = value.strip().lower()
    return cleaned if _EMAIL_RE.fullmatch(cleaned) else None


def normalize_phone(value: str | None, *, default_country_code: str = "") -> str | None:
    """Digits with a leading `+`, so the same number written three ways matches itself.

    Without a country code we can't safely invent one — "98765 43210" is a different number
    in different countries — so a national-format number is kept as its digits. Comparing
    those to each other is still exact, which is what identity resolution needs.
    """
    if not value:
        return None
    raw = value.strip()
    # A leading "+" can sit inside brackets — "(+91) 98765 43210" is the same number as
    # "+91 98765 43210", and treating it as national format would stop them matching.
    has_plus = raw.lstrip("([ ").startswith("+")
    digits = "".join(_DIGITS_RE.findall(raw))
    if len(digits) < 7:  # too short to be a real phone number
        return None
    if has_plus:
        return f"+{digits}"
    if default_country_code:
        return f"+{default_country_code}{digits}"
    return digits


def find_contact_hints(text: str) -> ContactHints:
    """The free pass: is there anything email- or phone-shaped in here at all?"""
    email_match = _EMAIL_RE.search(text or "")
    hints = ContactHints(email=email_match.group(0) if email_match else None)

    for candidate in _PHONE_RE.findall(text or ""):
        # An email's local part can look phone-ish; don't let it masquerade as one.
        if email_match and candidate.strip() in email_match.group(0):
            continue
        normalized = normalize_phone(candidate)
        if normalized:
            hints.phone = normalized
            break
    return hints


async def _resolve_provider(session: AsyncSession, org_id: uuid.UUID) -> ChatProvider:
    """The same small/fast model the memory summarizer uses — never the agent's own."""
    try:
        return await get_chat_provider(session, org_id, settings.summary_provider)
    except AppError:
        log.warning("crm_extract_provider_stubbed", provider=settings.summary_provider)
        return FakeChatProvider()


def _parse(content: str) -> ExtractedContact:
    """Tolerant of a model that wraps its JSON in prose or a code fence."""
    text = content.strip()
    if "{" in text and "}" in text:
        text = text[text.index("{") : text.rindex("}") + 1]
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return ExtractedContact()
    if not isinstance(data, dict):
        return ExtractedContact()

    name = data.get("name")
    return ExtractedContact(
        name=str(name).strip()[:255] if name and str(name).strip().lower() != "null" else None,
        email=normalize_email(data.get("email") if isinstance(data.get("email"), str) else None),
        phone=normalize_phone(data.get("phone") if isinstance(data.get("phone"), str) else None),
    )


async def extract_contact(
    session: AsyncSession, org_id: uuid.UUID, text: str, hints: ContactHints
) -> ExtractedContact:
    """One small LLM call over just this message — never the whole conversation.

    Its only jobs are pulling out a *name* stated near the contact details and tidying the
    formatting. The regex results are the floor: if the model returns nothing useful, we
    still keep what the pattern already found.
    """
    try:
        provider = await _resolve_provider(session, org_id)
        result = await provider.chat(
            ChatRequest(
                model=settings.summary_model,
                messages=[
                    Message(role="system", content=_SYSTEM),
                    Message(role="user", content=text[:2000]),
                ],
                temperature=0.0,
                max_tokens=200,
            )
        )
        extracted = _parse(result.content or "")
    except Exception as exc:  # extraction is best-effort; never fail the customer's turn
        log.warning("crm_extract_failed", error=str(exc))
        extracted = ExtractedContact()

    # Fall back to what the regex saw, so a useless model reply doesn't lose real data.
    return ExtractedContact(
        name=extracted.name,
        email=extracted.email or normalize_email(hints.email),
        phone=extracted.phone or hints.phone,
    )
