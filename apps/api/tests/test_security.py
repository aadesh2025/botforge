"""Phase 16.2 tests: security headers + rate-limited public surfaces."""

from __future__ import annotations

from httpx import AsyncClient


async def test_security_headers_present(client: AsyncClient) -> None:
    r = await client.get("/healthz")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["Referrer-Policy"] == "no-referrer"
    assert "default-src 'none'" in r.headers["Content-Security-Policy"]
    assert "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]


async def test_channel_webhook_rate_limited(client: AsyncClient, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    # Drop the webhook limit to something tiny and hammer the endpoint.
    from app.core import ratelimit

    async def _tiny_hit(key: str, limit: int, window: int) -> tuple[bool, int]:
        # Force the 3rd+ call in this scope to be throttled.
        _tiny_hit.calls = getattr(_tiny_hit, "calls", 0) + 1  # type: ignore[attr-defined]
        return (_tiny_hit.calls <= 2, 60)  # type: ignore[attr-defined]

    monkeypatch.setattr(ratelimit.limiter, "hit", _tiny_hit)

    import uuid

    cid = uuid.uuid4()
    codes = []
    for _ in range(4):
        resp = await client.post(f"/v1/channels/telegram/{cid}/webhook", json={})
        codes.append(resp.status_code)
    # First couple allowed through (then 404/verify path), later ones hit 429.
    assert 429 in codes
