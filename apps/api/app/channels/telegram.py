"""Telegram channel adapter (docs/07 §2)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.channels.base import BaseChannel, ContactProfile, InboundMessage, register
from app.core.logging import get_logger

log = get_logger("channels.telegram")


def _profile(msg: dict[str, Any]) -> ContactProfile:
    """Telegram puts the sender's identity straight in the update — no lookup needed."""
    user = msg.get("from") or {}
    chat = msg.get("chat") or {}
    src = user if user else chat
    name = " ".join(str(p) for p in (src.get("first_name"), src.get("last_name")) if p).strip()
    if not name:
        # Group chats have a title; a user with no first name still has a @handle.
        name = str(src.get("title") or src.get("username") or "")
    extra: dict[str, Any] = {}
    if src.get("username"):
        extra["username"] = str(src["username"])
    if src.get("language_code"):
        extra["locale"] = str(src["language_code"])
    # avatar_url stays null on purpose: Telegram serves profile photos from
    # api.telegram.org/file/bot<TOKEN>/… — persisting that URL would put the bot token
    # in the contacts table and hand it to every operator who can open the inbox.
    return ContactProfile(display_name=name or None, extra=extra)


class TelegramChannel(BaseChannel):
    type = "telegram"
    secret_fields = ("bot_token",)

    async def verify(
        self, channel: Any, headers: Mapping[str, str], body: bytes, query: Mapping[str, str]
    ) -> bool:
        # Telegram echoes the secret we registered via setWebhook.
        if not channel.webhook_secret:
            return True
        return bool(headers.get("x-telegram-bot-api-secret-token") == channel.webhook_secret)

    def parse_inbound(self, channel: Any, payload: dict[str, Any]) -> InboundMessage | None:
        msg = payload.get("message") or payload.get("edited_message")
        if not isinstance(msg, dict):
            return None
        text = msg.get("text")
        chat_id = (msg.get("chat") or {}).get("id")
        if text is None or chat_id is None:
            return None
        return InboundMessage(
            external_user_id=str(chat_id), text=str(text), raw=payload, profile=_profile(msg)
        )

    async def send(self, channel: Any, to: str, text: str) -> None:
        token = self.secret(channel, "bot_token")
        if not token:
            log.warning("telegram_no_token", channel=str(channel.id))
            return
        async with self._client(base_url=f"https://api.telegram.org/bot{token}") as client:
            await client.post("/sendMessage", json={"chat_id": to, "text": text})

    async def on_enable(self, channel: Any, *, api_base: str) -> None:
        token = self.secret(channel, "bot_token")
        if not token:
            log.warning("telegram_setwebhook_skipped_no_token", channel=str(channel.id))
            return
        url = f"{api_base.rstrip('/')}/v1/channels/telegram/{channel.id}/webhook"
        async with self._client(base_url=f"https://api.telegram.org/bot{token}") as client:
            await client.post(
                "/setWebhook",
                json={"url": url, "secret_token": channel.webhook_secret, "drop_pending_updates": True},
            )
        log.info("telegram_webhook_set", channel=str(channel.id), url=url)


register(TelegramChannel())
