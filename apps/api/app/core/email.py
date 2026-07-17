"""Email sending with a dev console backend.

The console backend both logs and records messages in an outbox, which tests inspect
to pull verification / reset / magic-link tokens without a real mail server.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger("email")


@dataclass(slots=True)
class EmailMessage:
    to: str
    subject: str
    body: str


class ConsoleEmailBackend:
    """Logs emails and keeps them in an in-memory outbox (dev/test only)."""

    def __init__(self) -> None:
        self.outbox: list[EmailMessage] = []

    async def send(self, message: EmailMessage) -> None:
        self.outbox.append(message)
        log.info("email_sent", to=message.to, subject=message.subject, backend="console")


@lru_cache
def get_email_backend() -> ConsoleEmailBackend:
    # Only the console backend exists so far; SMTP lands with production email (later phase).
    if settings.email_backend == "smtp":
        log.warning("smtp_backend_not_implemented", effect="falling back to console")
    return ConsoleEmailBackend()
