"""Rate limiter unit tests (in-memory fallback path — no Redis needed)."""

from __future__ import annotations

from app.core.ratelimit import RateLimiter


async def test_limiter_allows_up_to_limit_then_blocks() -> None:
    # Point at an unreachable Redis so it falls back to the in-memory limiter.
    limiter = RateLimiter("redis://127.0.0.1:6390/0")

    results = [await limiter.hit("k", limit=3, window=60) for _ in range(4)]
    allowed = [r[0] for r in results]
    assert allowed == [True, True, True, False]
    assert results[-1][1] > 0  # retry-after seconds on the blocked hit


async def test_limiter_separate_keys_are_independent() -> None:
    limiter = RateLimiter("redis://127.0.0.1:6390/0")
    assert (await limiter.hit("a", 1, 60))[0] is True
    assert (await limiter.hit("a", 1, 60))[0] is False
    assert (await limiter.hit("b", 1, 60))[0] is True
