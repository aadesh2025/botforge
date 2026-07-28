"""WhatsApp (Meta Cloud API) channel adapter (docs/07 §2)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.channels.base import BaseChannel, ContactProfile, InboundMessage, register
from app.channels.meta_signature import verify_challenge, verify_signature
from app.core.logging import get_logger

log = get_logger("channels.whatsapp")


class WhatsAppChannel(BaseChannel):
    type = "whatsapp"
    secret_fields = ("access_token", "app_secret")

    async def verify(
        self, channel: Any, headers: Mapping[str, str], body: bytes, query: Mapping[str, str]
    ) -> bool:
        return verify_signature(self.secret(channel, "app_secret"), headers, body)

    def verify_challenge(self, channel: Any, query: Mapping[str, str]) -> str | None:
        """Meta's GET webhook verification handshake → return hub.challenge on success."""
        return verify_challenge(channel, query)

    def parse_inbound(self, channel: Any, payload: dict[str, Any]) -> InboundMessage | None:
        try:
            value = payload["entry"][0]["changes"][0]["value"]
            msg = value["messages"][0]
            sender = msg["from"]
            text = msg["text"]["body"]
        except (KeyError, IndexError, TypeError):
            return None
        return InboundMessage(
            external_user_id=str(sender),
            text=str(text),
            raw=payload,
            profile=self._profile(value, str(sender)),
        )

    @staticmethod
    def _profile(value: dict[str, Any], sender: str) -> ContactProfile:
        """WhatsApp ships the contact's profile name with the message.

        There is no photo endpoint on the Cloud API, so ``avatar_url`` stays null — a
        platform limitation, not a gap to fill in later.
        """
        name: str | None = None
        for contact in value.get("contacts") or []:
            if isinstance(contact, dict) and (contact.get("profile") or {}).get("name"):
                name = str(contact["profile"]["name"])
                break
        return ContactProfile(display_name=name, extra={"phone": sender})

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
