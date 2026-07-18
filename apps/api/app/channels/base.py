"""Channel adapter interface, secret handling, and the registry."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.crypto import decrypt
from app.core.logging import get_logger
from app.models import Channel

log = get_logger("channels")


@dataclass
class InboundMessage:
    external_user_id: str
    text: str
    raw: dict[str, Any] = field(default_factory=dict)


class BaseChannel:
    """One messaging channel type. Subclasses implement verify / parse_inbound / send."""

    type: str = ""
    #: config keys that hold secrets (encrypted at rest, masked in API responses).
    secret_fields: tuple[str, ...] = ()

    def __init__(self) -> None:
        # Tests set this to an httpx.MockTransport; production leaves it None.
        self.transport: httpx.AsyncBaseTransport | None = None

    # ── secrets ──────────────────────────────────────────────────────────────
    def secret(self, channel: Channel, field_name: str) -> str | None:
        raw = channel.config.get(field_name)
        if not raw:
            return None
        try:
            return decrypt(str(raw))
        except Exception:  # tolerate a plaintext value (dev convenience)
            return str(raw)

    def missing_secrets(self, channel: Channel) -> list[str]:
        return [f for f in self.secret_fields if not channel.config.get(f)]

    # ── inbound / outbound ───────────────────────────────────────────────────
    async def verify(
        self, channel: Channel, headers: Mapping[str, str], body: bytes, query: Mapping[str, str]
    ) -> bool:
        return True

    def parse_inbound(self, channel: Channel, payload: dict[str, Any]) -> InboundMessage | None:
        raise NotImplementedError

    async def send(self, channel: Channel, to: str, text: str) -> None:
        raise NotImplementedError

    async def on_enable(self, channel: Channel, *, api_base: str) -> None:
        """Optional hook run when a channel is enabled (e.g. Telegram setWebhook)."""
        return None

    def _client(self, **kw: Any) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=20.0, transport=self.transport, **kw)


CHANNELS: dict[str, BaseChannel] = {}


def register(channel: BaseChannel) -> BaseChannel:
    CHANNELS[channel.type] = channel
    return channel


def get_channel(channel_type: str) -> BaseChannel | None:
    return CHANNELS.get(channel_type)
