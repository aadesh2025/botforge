"""Reachability probes for /readyz. Graceful: never raise, just report status."""

from __future__ import annotations

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger("probes")


async def check_database() -> bool:
    try:
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine

        engine = create_async_engine(settings.database_url, pool_pre_ping=True)
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        finally:
            await engine.dispose()
    except Exception as exc:
        log.warning("database_unreachable", error=str(exc))
        return False


async def check_redis() -> bool:
    try:
        from redis.asyncio import from_url

        client = from_url(settings.redis_url)
        try:
            await client.ping()
            return True
        finally:
            await client.aclose()
    except Exception as exc:
        log.warning("redis_unreachable", error=str(exc))
        return False
