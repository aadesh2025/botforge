"""Shared pytest fixtures.

DB-backed tests run against the real Postgres (migrated) inside a transaction that is
rolled back after each test, so nothing persists and tests stay isolated.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings
from app.core.email import get_email_backend
from app.db.session import get_session
from app.main import create_app

# Keep rate limiting out of the way of functional tests; it's unit-tested separately.
settings.auth_rate_limit = 100_000


@pytest.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(settings.database_url)
    conn = await engine.connect()
    trans = await conn.begin()
    session = AsyncSession(bind=conn, expire_on_commit=False)
    try:
        yield session
    finally:
        await session.close()
        await trans.rollback()
        await conn.close()
        await engine.dispose()


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    app = create_app()

    async def _override_session() -> AsyncIterator[AsyncSession]:
        yield db_session  # shared across the test; no commit, rolled back at teardown

    app.dependency_overrides[get_session] = _override_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _allow_self_serve_orgs() -> AsyncIterator[None]:
    """Let tests bootstrap a tenant through the public API.

    Production is staff-only with no first-org exception (`create_org`), but nearly every test
    file starts by signing up a throwaway user and POSTing /v1/orgs to get an isolated org.
    Making each of those users staff would be both a large edit and a lie about what the test
    is exercising. `tests/test_org_creation_gate.py` turns this back off and asserts the real
    production rule, so the gate is still covered.
    """
    from app.core.config import settings

    previous = settings.allow_self_serve_orgs
    settings.allow_self_serve_orgs = True
    yield
    settings.allow_self_serve_orgs = previous


@pytest.fixture(autouse=True)
def _clear_email_outbox() -> AsyncIterator[None]:
    get_email_backend().outbox.clear()
    yield
    get_email_backend().outbox.clear()


@pytest.fixture(autouse=True)
def _reset_rate_limiter() -> None:
    """Reset the rate limiter between tests.

    Clears the in-memory buckets and drops any cached async Redis client so it rebinds to the
    current test's event loop (the sync-TestClient WS test closes the previous one).
    """
    from app.core.ratelimit import limiter

    limiter._mem.clear()
    limiter._redis = None
    limiter._checked = False
