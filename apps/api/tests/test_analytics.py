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
    # Analytics groups by UTC date (matches how timestamps are stored) — compare in UTC, not local.
    assert by_day.json()[0]["key"] == dt.datetime.now(dt.UTC).date().isoformat()


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

    written = await rollup_usage(db_session, uuid.UUID(org_id), dt.datetime.now(dt.UTC).date())
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


# ── Per-channel breakdown ───────────────────────────────────────────────────────────
async def _connect_channel(client: AsyncClient, headers: dict[str, str], aid: str, ctype: str) -> str:
    """Connect + enable a channel. Config is irrelevant here — these tests never deliver
    through it, they only care that an *enabled* channel exists to report on."""
    ch = await client.post(
        "/v1/channels", json={"agent_id": aid, "type": ctype, "config": {}}, headers=headers
    )
    assert ch.status_code == 201, ch.text
    cid = ch.json()["id"]
    await client.post(f"/v1/channels/{cid}/enable", headers=headers)
    return cid


async def test_overview_by_channel_includes_connected_but_empty(client: AsyncClient) -> None:
    """The case this breakdown exists for: WhatsApp gets connected with real credentials
    days before anyone messages it. It must read as a zero row, not disappear."""
    headers, _ = await _headers(client, "ch-empty@example.com")
    aid = await _fake_agent(client, headers)
    await _connect_channel(client, headers, aid, "whatsapp")

    # Traffic on one channel only (dashboard chat → the `web` conversation channel).
    await client.post(f"/v1/agents/{aid}/chat", json={"message": "hi", "stream": False}, headers=headers)

    ov = (await client.get("/v1/analytics/overview", headers=headers)).json()
    by_channel = {b["channel"]: b for b in ov["by_channel"]}

    # Connected-but-silent → a real zero row, with no divide-by-zero on the rates.
    assert "whatsapp" in by_channel, "an enabled channel must appear even with no traffic"
    empty = by_channel["whatsapp"]
    assert empty["conversations"] == 0
    assert empty["messages"] == 0
    assert empty["cost_micros"] == 0
    assert empty["handoff_rate"] == 0.0
    assert empty["resolution_rate"] == 0.0

    # The widget is inherent to every agent, so it's always reportable too.
    assert "widget" in by_channel

    # And the channel that actually has traffic carries the real numbers.
    populated = next(b for b in ov["by_channel"] if b["conversations"] > 0)
    assert populated["messages"] == 2  # 1 user + 1 assistant
    assert populated["tokens_prompt"] == 10
    assert populated["resolution_rate"] == 1.0

    # Per-channel conversations reconcile with the flat total.
    assert sum(b["conversations"] for b in ov["by_channel"]) == ov["conversations"]


async def test_by_channel_omits_disabled_channels(client: AsyncClient) -> None:
    """A channel that was connected and then switched off isn't somewhere traffic can
    arrive, so it shouldn't sit in the breakdown implying it's live."""
    headers, _ = await _headers(client, "ch-disabled@example.com")
    aid = await _fake_agent(client, headers)
    cid = await _connect_channel(client, headers, aid, "telegram")
    await client.post(f"/v1/channels/{cid}/disable", headers=headers)

    ov = (await client.get("/v1/analytics/overview", headers=headers)).json()
    assert "telegram" not in {b["channel"] for b in ov["by_channel"]}


async def test_usage_group_by_channel(client: AsyncClient) -> None:
    headers, _ = await _headers(client, "ch-usage@example.com")
    aid = await _fake_agent(client, headers)
    await _connect_channel(client, headers, aid, "instagram")
    await client.post(f"/v1/agents/{aid}/chat", json={"message": "hi", "stream": False}, headers=headers)

    buckets = (await client.get("/v1/analytics/usage?group_by=channel", headers=headers)).json()
    by_key = {b["key"]: b for b in buckets}

    populated = next(b for b in buckets if b["requests"] > 0)
    assert populated["tokens_prompt"] == 10

    # Zero-filled the same way the overview breakdown is.
    assert by_key["instagram"]["requests"] == 0
    assert by_key["instagram"]["tokens_prompt"] == 0
    assert by_key["instagram"]["cost_micros"] == 0


async def test_channel_filter_narrows_results(client: AsyncClient) -> None:
    headers, _ = await _headers(client, "ch-filter@example.com")
    aid = await _fake_agent(client, headers)
    await _connect_channel(client, headers, aid, "instagram")
    await client.post(f"/v1/agents/{aid}/chat", json={"message": "hi", "stream": False}, headers=headers)

    # An enabled channel with no traffic: real response, all zeros, no error.
    scoped = (await client.get("/v1/analytics/overview?channel=instagram", headers=headers)).json()
    assert scoped["conversations"] == 0
    assert scoped["messages"] == 0
    assert [b["channel"] for b in scoped["by_channel"]] == ["instagram"]

    # An unknown channel is an empty result, not a 422 — `channel` is free text because
    # conversations still carry legacy values (`web`, `api`).
    unknown = await client.get("/v1/analytics/overview?channel=nope", headers=headers)
    assert unknown.status_code == 200
    assert unknown.json()["conversations"] == 0
    assert unknown.json()["by_channel"] == []


async def test_csv_channel_export(client: AsyncClient) -> None:
    headers, _ = await _headers(client, "ch-csv@example.com")
    aid = await _fake_agent(client, headers)
    await _connect_channel(client, headers, aid, "facebook")
    await client.post(f"/v1/agents/{aid}/chat", json={"message": "x", "stream": False}, headers=headers)

    csv = await client.get("/v1/analytics/export?type=channels", headers=headers)
    assert csv.status_code == 200
    assert "text/csv" in csv.headers["content-type"]
    lines = csv.text.splitlines()
    assert lines[0] == (
        "channel,conversations,messages,tokens_prompt,tokens_completion,cost_micros,"
        "handoff_rate,resolution_rate"
    )
    # The connected-but-empty channel is exported as a zero row, not dropped.
    fb = next(line for line in lines[1:] if line.startswith("facebook,"))
    assert fb == "facebook,0,0,0,0,0,0.0,0.0"


async def test_overview_counts_dashboard_conversations_as_users(client: AsyncClient) -> None:
    """`users` counted distinct channel_user_id, which only channel/widget conversations
    carry — so an org whose traffic is all dashboard reported 0 users next to N
    conversations. An untracked conversation is one person."""
    headers, _ = await _headers(client, "users-metric@example.com")
    aid = await _fake_agent(client, headers)

    for text in ("first question", "second question"):
        r = await client.post(
            f"/v1/agents/{aid}/chat", json={"message": text, "stream": False}, headers=headers
        )
        assert r.status_code == 200, r.text

    ov = (await client.get("/v1/analytics/overview", headers=headers)).json()
    assert ov["conversations"] == 2
    assert ov["users"] == ov["conversations"]
