"""A tiny in-process async pub/sub for WebSocket fan-out.

Single-process only (dev/one-node). For multi-process, swap the body for Redis pub/sub behind
this same interface — callers only use `subscribe` / `unsubscribe` / `publish`.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any


class Hub:
    def __init__(self) -> None:
        self._subs: dict[str, set[asyncio.Queue[dict[str, Any]]]] = {}

    def subscribe(self, topic: str) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=200)
        self._subs.setdefault(topic, set()).add(queue)
        return queue

    def unsubscribe(self, topic: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        subs = self._subs.get(topic)
        if subs is not None:
            subs.discard(queue)
            if not subs:
                self._subs.pop(topic, None)

    async def publish(self, topic: str, event: dict[str, Any]) -> None:
        for queue in list(self._subs.get(topic, set())):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass  # a slow subscriber shouldn't block the publisher


hub = Hub()


def conv_topic(conversation_id: uuid.UUID | str) -> str:
    return f"conv:{conversation_id}"


def inbox_topic(org_id: uuid.UUID | str) -> str:
    return f"inbox:{org_id}"
