"""Team performance: per-teammate inbox workload, derived from existing handoff data."""

from __future__ import annotations

import datetime as dt
import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Handoff


async def _headers(client: AsyncClient, email: str) -> tuple[dict[str, str], str]:
    signup = await client.post("/v1/auth/signup", json={"email": email, "password": "password123"})
    token = signup.json()["access_token"]
    o = await client.post("/v1/orgs", json={"name": "PerfOrg"}, headers={"Authorization": f"Bearer {token}"})
    headers = {"Authorization": f"Bearer {token}", "X-Org-Id": o.json()["id"]}
    me = await client.get("/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    return headers, str(me.json()["user"]["id"])


async def _handed_off(client: AsyncClient, headers: dict[str, str], key: str) -> str:
    chat = await client.post(
        f"/v1/public/agents/{key}/chat", json={"message": "I want a human agent", "stream": False}
    )
    return str(chat.json()["conversation_id"])


async def _agent(client: AsyncClient, headers: dict[str, str]) -> str:
    agent = await client.post("/v1/agents", json={"name": "Perf Bot"}, headers=headers)
    aid = agent.json()["id"]
    await client.patch(
        f"/v1/agents/{aid}/versions/1",
        json={
            "fallback_message": "Connecting you to a teammate now.",
            "model_config": {"provider": "fake", "model": "fake-1"},
            "features": {"tools_enabled": False, "memory_enabled": True, "handoff_enabled": True},
        },
        headers=headers,
    )
    return str(agent.json()["public_key"])


async def test_reports_handoffs_replies_and_closures_per_teammate(client: AsyncClient) -> None:
    headers, uid = await _headers(client, "perf1@example.com")
    key = await _agent(client, headers)

    cid = await _handed_off(client, headers, key)
    await client.post(f"/v1/inbox/conversations/{cid}/takeover", headers=headers)
    await client.post(
        f"/v1/inbox/conversations/{cid}/messages", json={"text": "On it."}, headers=headers
    )
    await client.post(f"/v1/inbox/conversations/{cid}/close", headers=headers)

    # A second handoff taken over but left open.
    second = await _handed_off(client, headers, key)
    await client.post(f"/v1/inbox/conversations/{second}/takeover", headers=headers)

    rows = (await client.get("/v1/analytics/agents", headers=headers)).json()
    assert len(rows) == 1
    me = rows[0]
    assert me["user_id"] == uid
    assert me["name"]  # falls back to the signup email when there's no full name
    assert me["handoffs"] == 2
    assert me["closed_count"] == 1
    # A reply happened, so there's a first-response time; it isn't negative.
    assert me["avg_first_response_ms"] is not None and me["avg_first_response_ms"] >= 0


async def test_unassigned_handoffs_are_not_attributed_to_anyone(client: AsyncClient) -> None:
    """A queued handoff nobody has taken shouldn't inflate someone's numbers."""
    headers, _uid = await _headers(client, "perf2@example.com")
    key = await _agent(client, headers)
    await _handed_off(client, headers, key)  # never taken over

    assert (await client.get("/v1/analytics/agents", headers=headers)).json() == []


async def test_durations_are_null_not_zero_when_there_is_nothing_to_average(
    client: AsyncClient,
) -> None:
    """A teammate who has never resolved anything hasn't achieved a 0ms resolution time."""
    headers, _uid = await _headers(client, "perf3@example.com")
    key = await _agent(client, headers)
    cid = await _handed_off(client, headers, key)
    await client.post(f"/v1/inbox/conversations/{cid}/takeover", headers=headers)

    row = (await client.get("/v1/analytics/agents", headers=headers)).json()[0]
    assert row["handoffs"] == 1
    assert row["avg_first_response_ms"] is None  # never replied
    assert row["avg_resolution_ms"] is None  # never resolved
    assert row["closed_count"] == 0


async def test_resolution_time_is_measured(client: AsyncClient, db_session: AsyncSession) -> None:
    headers, _uid = await _headers(client, "perf4@example.com")
    key = await _agent(client, headers)
    cid = await _handed_off(client, headers, key)
    await client.post(f"/v1/inbox/conversations/{cid}/takeover", headers=headers)

    # Back-date the handoff so the elapsed time is unambiguous.
    handoff = (
        await db_session.get(Handoff, uuid.UUID(str((
            await client.get(f"/v1/inbox/conversations/{cid}", headers=headers)
        ).json()["handoff"]["id"])))
    )
    handoff.created_at = dt.datetime.now(tz=dt.UTC) - dt.timedelta(minutes=10)
    await db_session.flush()

    await client.post(f"/v1/inbox/conversations/{cid}/handback", headers=headers)

    row = (await client.get("/v1/analytics/agents", headers=headers)).json()[0]
    assert row["avg_resolution_ms"] is not None
    # ~10 minutes, allowing for test execution time.
    assert 9 * 60_000 < row["avg_resolution_ms"] < 12 * 60_000


async def test_date_range_excludes_older_handoffs(client: AsyncClient) -> None:
    headers, _uid = await _headers(client, "perf5@example.com")
    key = await _agent(client, headers)
    cid = await _handed_off(client, headers, key)
    await client.post(f"/v1/inbox/conversations/{cid}/takeover", headers=headers)

    future = (dt.datetime.now(tz=dt.UTC).date() + dt.timedelta(days=1)).isoformat()
    scoped = await client.get(
        "/v1/analytics/agents", params={"from": future, "to": future}, headers=headers
    )
    assert scoped.json() == []


async def test_requires_analytics_permission(client: AsyncClient) -> None:
    headers, _uid = await _headers(client, "perf6@example.com")
    r = await client.get("/v1/analytics/agents", headers=headers)
    assert r.status_code == 200  # owner has ANALYTICS_VIEW
    assert (await client.get("/v1/analytics/agents")).status_code == 401
