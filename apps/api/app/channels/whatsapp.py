"""WhatsApp (Meta Cloud API) channel adapter (docs/07 §2)."""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Mapping
from typing import Any

from app.channels.base import BaseChannel, InboundMessage, register
from app.core.logging import get_logger

log = get_logger("channels.whatsapp")


class WhatsAppChannel(BaseChannel):
    type = "whatsapp"
    secret_fields = ("access_token", "app_secret")

    async def verify(
        self, channel: Any, headers: Mapping[str, str], body: bytes, query: Mapping[str, str]
    ) -> bool:
        secret = self.secret(channel, "app_secret")
        if not secret:
            return True
        provided = headers.get("x-hub-signature-256", "")
        expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, provided)

    def verify_challenge(self, channel: Any, query: Mapping[str, str]) -> str | None:
        """Meta's GET webhook verification handshake → return hub.challenge on success."""
        if query.get("hub.mode") == "subscribe" and query.get("hub.verify_token") == channel.config.get(
            "verify_token"
        ):
            return query.get("hub.challenge")
        return None

    def parse_inbound(self, channel: Any, payload: dict[str, Any]) -> InboundMessage | None:
        try:
            value = payload["entry"][0]["changes"][0]["value"]
            msg = value["messages"][0]
            sender = msg["from"]
            text = msg["text"]["body"]
        except (KeyError, IndexError, TypeError):
            return None
        return InboundMessage(external_user_id=str(sender), text=str(text), raw=payload)

    async def send(self, channel: Any, to: str, text: str) -> None:
        token = self.secret(channel, "access_token")
        phone_number_id = channel.config.get("phone_number_id")
        if not token or not phone_number_id:
            log.warning("whatsapp_send_skipped_missing_config", channel=str(channel.id))
            return
        async with self._client(base_url="https://graph.facebook.com/v19.0") as client:
            await client.post(
                f"/{phone_number_id}/messages",
                headers={"Authorization": f"Bearer {token}"},
                json={"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": text}},
            )


register(WhatsAppChannel())
