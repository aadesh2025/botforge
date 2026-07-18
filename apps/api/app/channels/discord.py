"""Discord channel adapter — interaction (slash-command) mode with Ed25519 verify (docs/07 §2).

Discord replies are the interaction HTTP response (handled by the router), so `send` is a no-op.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from app.channels.base import BaseChannel, InboundMessage, register
from app.core.logging import get_logger

log = get_logger("channels.discord")


class DiscordChannel(BaseChannel):
    type = "discord"
    secret_fields = ("bot_token",)  # public_key is public → stored plaintext

    async def verify(
        self, channel: Any, headers: Mapping[str, str], body: bytes, query: Mapping[str, str]
    ) -> bool:
        public_key = channel.config.get("public_key")
        if not public_key:
            return True
        signature = headers.get("x-signature-ed25519", "")
        timestamp = headers.get("x-signature-timestamp", "")
        try:
            verify_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key))
            verify_key.verify(bytes.fromhex(signature), timestamp.encode() + body)
            return True
        except (InvalidSignature, ValueError):
            return False

    def parse_inbound(self, channel: Any, payload: dict[str, Any]) -> InboundMessage | None:
        # type 2 = APPLICATION_COMMAND (slash command). type 1 (PING) is handled by the router.
        if payload.get("type") != 2:
            return None
        data = payload.get("data") or {}
        options = {o.get("name"): o.get("value") for o in data.get("options", [])}
        text = options.get("message") or options.get("text") or options.get("prompt")
        user = (payload.get("member") or {}).get("user") or payload.get("user") or {}
        uid = user.get("id") or payload.get("channel_id")
        if not text or not uid:
            return None
        return InboundMessage(external_user_id=str(uid), text=str(text), raw=payload)

    async def send(self, channel: Any, to: str, text: str) -> None:
        # No-op: Discord interaction replies are returned inline in the webhook response.
        return None


register(DiscordChannel())
