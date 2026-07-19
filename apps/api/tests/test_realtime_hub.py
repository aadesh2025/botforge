"""Realtime hub: local delivery always works; Redis bridges delivery across nodes (ADR-028)."""

from __future__ import annotations

import asyncio

import pytest

from app.core.config import settings
from app.realtime.hub import Hub, conv_topic


@pytest.mark.asyncio
async def test_local_delivery_without_redis() -> None:
    hub = Hub()
    q = hub.subscribe(conv_topic("c1"))
    await hub.publish(conv_topic("c1"), {"type": "token", "content": "hi"})
    assert await asyncio.wait_for(q.get(), timeout=1) == {"type": "token", "content": "hi"}
    hub.unsubscribe(conv_topic("c1"), q)


@pytest.mark.asyncio
async def test_no_delivery_after_unsubscribe() -> None:
    hub = Hub()
    q = hub.subscribe(conv_topic("c2"))
    hub.unsubscribe(conv_topic("c2"), q)
    await hub.publish(conv_topic("c2"), {"type": "x"})
    assert q.empty()


@pytest.mark.asyncio
async def test_cross_node_delivery_over_redis() -> None:
    """A publish on node A reaches a subscriber on node B (simulates two API replicas)."""
    try:
        from redis.asyncio import from_url

        probe = from_url(settings.redis_url)
        await probe.ping()
        await probe.aclose()
    except Exception:
        pytest.skip("Redis not available")

    node_a = Hub()
    node_b = Hub()
    await node_a.connect(settings.redis_url)
    await node_b.connect(settings.redis_url)
    try:
        # Subscriber lives on node B; publisher is node A (no local subscriber on A).
        q = node_b.subscribe(conv_topic("shared"))
        await asyncio.sleep(0.2)  # let B's reader finish subscribing
        await node_a.publish(conv_topic("shared"), {"type": "handback", "content": "resumed"})
        got = await asyncio.wait_for(q.get(), timeout=3)
        assert got == {"type": "handback", "content": "resumed"}
    finally:
        await node_a.close()
        await node_b.close()
