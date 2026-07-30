"""Email sending: a dev console backend and real delivery over SMTP.

The console backend both logs and records messages in an outbox, which tests inspect
to pull verification / reset / magic-link / invitation tokens without a real mail server.

Real delivery is plain SMTP on purpose. Every transactional provider (Resend, Postmark,
SendGrid, Mailgun, SES) exposes an SMTP relay with the same five settings, so switching
provider is an env change and never a code change.
"""

from __future__ import annotations

from dataclasses import dataclass
from email.message import EmailMessage as MimeMessage
from functools import lru_cache
from typing import Protocol

from app.core.config import settings
from app.core.errors import AppError
from app.core.logging import get_logger

log = get_logger("email")


@dataclass(slots=True)
class EmailMessage:
    to: str
    subject: str
    body: str
    #: Optional HTML alternative. Plain text alone renders as broken/spammy in most inboxes.
    html_body: str | None = None


class EmailBackend(Protocol):
    async def send(self, message: EmailMessage) -> None: ...


class ConsoleEmailBackend:
    """Logs emails and keeps them in an in-memory outbox (dev/test only)."""

    def __init__(self) -> None:
        self.outbox: list[EmailMessage] = []

    async def send(self, message: EmailMessage) -> None:
        self.outbox.append(message)
        log.info("email_sent", to=message.to, subject=message.subject, backend="console")


class SmtpEmailBackend:
    """Real delivery via any SMTP relay (Resend, Postmark, SendGrid, SES, Mailgun, ...)."""

    async def send(self, message: EmailMessage) -> None:
        import aiosmtplib

        host = settings.smtp_host.strip()
        sender = settings.smtp_from.strip()
        if not (host and sender):
            # A missing [HUMAN] secret fails loudly rather than silently dropping the mail
            # (CLAUDE.md §7) — a swallowed invitation is indistinguishable from a delivered one.
            log.error("smtp_not_configured", to=message.to, subject=message.subject)
            raise AppError("email.not_configured", "Email sending is not configured.", 500)

        mime = MimeMessage()
        mime["From"] = sender
        mime["To"] = message.to
        mime["Subject"] = message.subject
        mime.set_content(message.body)  # plain-text part
        if message.html_body:
            mime.add_alternative(message.html_body, subtype="html")

        # 465 is implicit TLS (TLS from the first byte); 587 and friends negotiate STARTTLS.
        # Providers publish both, so picking from the port keeps "it works" from depending on
        # the operator knowing which flag their relay wants. Either way TLS is required —
        # never hand credentials to a plaintext connection. For a local relay with no TLS at
        # all, use EMAIL_BACKEND=console; that's what it's for.
        implicit_tls = settings.smtp_port == 465
        try:
            await aiosmtplib.send(
                mime,
                hostname=host,
                port=settings.smtp_port,
                username=settings.smtp_user.strip() or None,
                password=settings.smtp_pass.strip() or None,
                start_tls=not implicit_tls,
                use_tls=implicit_tls,
            )
        except Exception:
            log.exception("email_send_failed", to=message.to, subject=message.subject)
            raise
        log.info("email_sent", to=message.to, subject=message.subject, backend="smtp")


@lru_cache
def get_email_backend() -> EmailBackend:
    if settings.email_backend == "smtp":
        return SmtpEmailBackend()
    return ConsoleEmailBackend()


async def queue_email(message: EmailMessage) -> None:
    """Hand an email off for delivery without ever failing the caller's request.

    Console mode sends inline: the outbox is in-memory, so there is nothing to protect the
    request from, and tests keep reading `get_email_backend().outbox` synchronously.

    Real SMTP goes to the Celery worker, so a slow or dead relay can't hang or 500 a signup,
    invite, reset or magic-link request. Enqueue failures are logged, never raised.

    Eager mode also sends inline, deliberately **not** via `.delay()`: eager tasks execute in
    the caller's thread, and every task in `app.worker.tasks` drives its coroutine with
    `asyncio.run()`, which raises inside an already-running event loop (the same trap that
    silently broke eager ingestion — see CLAUDE.md §12).
    """
    if settings.email_backend == "console" or settings.celery_task_always_eager:
        await get_email_backend().send(message)
        return

    import anyio
    from anyio import to_thread

    from app.worker.tasks import send_email_task

    def _enqueue() -> None:
        send_email_task.apply_async(
            args=[message.to, message.subject, message.body, message.html_body],
            retry=False,
        )

    # Enqueueing is blocking socket I/O, so it runs off the event loop — on the loop it would
    # stall every other in-flight request, not just this one.
    #
    # And it is *time-bounded*. Measured against a dead broker: kombu re-attempts the
    # connection 20 times with 1s sleeps whatever `retry=False` says, which turned a signup
    # into a 30-second hang. The timeout abandons that thread (it finishes or gives up on its
    # own, harmlessly) and lets the request carry on — losing a queued email is very much
    # better than losing the signup that triggered it.
    try:
        with anyio.move_on_after(settings.email_enqueue_timeout_seconds) as scope:
            await to_thread.run_sync(_enqueue, abandon_on_cancel=True)
        if scope.cancelled_caught:
            log.error("email_enqueue_timeout", to=message.to, subject=message.subject)
    except Exception:
        log.exception("email_enqueue_failed", to=message.to, subject=message.subject)
