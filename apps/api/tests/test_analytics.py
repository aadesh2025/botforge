"""Phase 14 tests: analytics aggregation + usage rollups (real numbers from the messages table)."""

from __future__ import annotations

import datetime as dt
import uuid

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import UsageRecord
from app.worker.rollup import refresh_quota, rollup_usage


async def _headers(client: AsyncClient, email: str = "an@example.com") -> tuple[dict[str, str], str]:
    signup = await client.post("/v1/auth/signup", json={"email": email, "password": "password123"})
    token = signup.json()["access_token"]
    org = await client.post("/v1/orgs", json={"name": "AnOrg"}, headers={"Authorization": f"Bearer {token}"})
    org_id = org.json()["id"]
    return {"Authorization": f"Bearer {token}", "X-Org-Id": org_id}, org_id


async def _fake_agent(client: AsyncClient, headers: dict[str, str], handoff: bool = False) -> str:
    agent = await client.post("/v1/agents", json={"name": "Metrics Bot"}, headers=headers)
    aid = agent.json()["id"]
    await client.patch(
        f"/v1/agents/{aid}/versions/1",
        json={
            "model_config": {"provider": "fake", "model": "fake-1"},
            "features": {"tools_enabled": False, "memory_enabled": True, "handoff_enabled": handoff},
        },
        headers=headers,
    )
    return aid


async def test_overview_matches_messages(client: AsyncClient) -> None:
    headers, _ = await _headers(client)
    aid = await _fake_agent(client, headers)
    r1 = await client.post(f"/v1/agents/{aid}/chat", json={"message": "hello", "stream": False}, headers=headers)
    cid = r1.json()["conversation_id"]
    await client.post(
        f"/v1/agents/{aid}/chat", json={"message": "again", "conversation_id": cid, "stream": False}, headers=headers
    )

    ov = await client.get("/v1/analytics/overview", headers=headers)
    assert ov.status_code == 200, ov.text
    data = ov.json()
    assert data["conversations"] == 1
    assert data["messages"] == 4  # 2 user + 2 assistant
    assert data["tokens_prompt"] == 20  # fake provider: 10 prompt tokens per assistant turn
    assert data["handoff_rate"] == 0.0
    assert data["resolution_rate"] == 1.0


async def test_usage_grouping(client: AsyncClient) -> None:
    headers, _ = await _headers(client, "an2@example.com")
    aid = await _fake_agent(client, headers)
    await client.post(f"/v1/agents/{aid}/chat", json={"message": "hi", "stream": False}, headers=headers)

    by_provider = await client.get("/v1/analytics/usage?group_by=provider", headers=headers)
    buckets = by_provider.json()
    assert buckets and buckets[0]["key"] == "fake"
    assert buckets[0]["requests"] == 1
    assert buckets[0]["tokens_prompt"] == 10

    by_day = await client.get("/v1/analytics/usage?group_by=day", headers=headers)
    assert by_day.json()[0]["key"] == dt.date.today().isoformat()


async def test_latency_and_top_questions(client: AsyncClient) -> None:
    headers, _ = await _headers(client, "an3@example.com")
    aid = await _fake_agent(client, headers)
    await client.post(f"/v1/agents/{aid}/chat", json={"message": "repeat me", "stream": False}, headers=headers)
    await client.post(f"/v1/agents/{aid}/chat", json={"message": "repeat me", "stream": False}, headers=headers)

    lat = await client.get("/v1/analytics/latency", headers=headers)
    assert lat.json()["count"] == 2

    top = await client.get("/v1/analytics/top-questions", headers=headers)
    q = next(x for x in top.json() if x["question"] == "repeat me")
    assert q["count"] == 2


async def test_unanswered_from_handoffs(client: AsyncClient) -> None:
    headers, _ = await _headers(client, "an4@example.com")
    agent = await client.post("/v1/agents", json={"name": "HO Bot"}, headers=headers)
    aid = agent.json()["id"]
    key = agent.json()["public_key"]
    await client.patch(
        f"/v1/agents/{aid}/versions/1",
        json={
            "model_config": {"provider": "fake", "model": "fake-1"},
            "features": {"tools_enabled": False, "memory_enabled": True, "handoff_enabled": True},
        },
        headers=headers,
    )
    # Keyword handoff fires on the widget/public inbound path.
    await client.post(f"/v1/public/agents/{key}/chat", json={"message": "I want a human agent", "stream": False})
    un = await client.get("/v1/analytics/unanswered", headers=headers)
    assert any("human agent" in x["question"] for x in un.json())


async def test_csv_export(client: AsyncClient) -> None:
    headers, _ = await _headers(client, "an5@example.com")
    aid = await _fake_agent(client, headers)
    await client.post(f"/v1/agents/{aid}/chat", json={"message": "x", "stream": False}, headers=headers)
    csv = await client.get("/v1/analytics/export?type=usage", headers=headers)
    assert csv.status_code == 200
    assert "text/csv" in csv.headers["content-type"]
    assert csv.text.splitlines()[0] == "date,provider,model,tokens_prompt,tokens_completion,requests,cost_micros"


async def test_rollup_matches_live_totals(client: AsyncClient, db_session: AsyncSession) -> None:
    headers, org_id = await _headers(client, "an6@example.com")
    aid = await _fake_agent(client, headers)
    await client.post(f"/v1/agents/{aid}/chat", json={"message": "one", "stream": False}, headers=headers)
    await client.post(f"/v1/agents/{aid}/chat", json={"message": "two", "stream": False}, headers=headers)

    written = await rollup_usage(db_session, uuid.UUID(org_id), dt.date.today())
    assert written == 1  # one (agent, provider, model) bucket

    total = (
        await db_session.execute(
            select(
                func.sum(UsageRecord.tokens_prompt),
                func.sum(UsageRecord.requests),
            ).where(UsageRecord.organization_id == uuid.UUID(org_id))
        )
    ).one()
    assert int(total[0]) == 20  # 2 assistant turns x 10 prompt tokens
    assert int(total[1]) == 2

    tokens_used, crossed = await refresh_quota(db_session, uuid.UUID(org_id))
    assert tokens_used >= 20
    assert crossed is False  # no token_limit set
