"""Slack channel adapter (docs/07 §2)."""

from __future__ import annotations

import hashlib
import hmac
import time
from collections.abc import Mapping
from typing import Any

from app.channels.base import BaseChannel, InboundMessage, register
from app.core.logging import get_logger

log = get_logger("channels.slack")


class SlackChannel(BaseChannel):
    type = "slack"
    secret_fields = ("bot_token", "signing_secret")

    async def verify(
        self, channel: Any, headers: Mapping[str, str], body: bytes, query: Mapping[str, str]
    ) -> bool:
        secret = self.secret(channel, "signing_secret")
        if not secret:
            return True
        ts = headers.get("x-slack-request-timestamp", "")
        try:
            if abs(time.time() - int(float(ts))) > 300:  # replay protection
                return False
        except ValueError:
            return False
        base = b"v0:" + ts.encode() + b":" + body
        expected = "v0=" + hmac.new(secret.encode(), base, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, headers.get("x-slack-signature", ""))

    def parse_inbound(self, channel: Any, payload: dict[str, Any]) -> InboundMessage | None:
        event = payload.get("event") or {}
        if event.get("type") not in ("app_mention", "message"):
            return None
        if event.get("bot_id") or event.get("subtype"):  # ignore bot echoes / edits
            return None
        text = event.get("text")
        slack_channel = event.get("channel")
        if not text or not slack_channel:
            return None
        return InboundMessage(external_user_id=str(slack_channel), text=str(text), raw=payload)

    async def send(self, channel: Any, to: str, text: str) -> None:
        token = self.secret(channel, "bot_token")
        if not token:
            log.warning("slack_send_skipped_no_token", channel=str(channel.id))
            return
        async with self._client(base_url="https://slack.com/api") as client:
            await client.post(
                "/chat.postMessage",
                headers={"Authorization": f"Bearer {token}"},
                json={"channel": to, "text": text},
            )


register(SlackChannel())
