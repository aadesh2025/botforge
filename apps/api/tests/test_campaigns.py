"""Campaigns: proactive widget triggers live; outbound broadcasts deliberately can't send."""

from __future__ import annotations

from httpx import AsyncClient


async def _headers(client: AsyncClient, email: str, org: str = "CampOrg") -> dict[str, str]:
    signup = await client.post("/v1/auth/signup", json={"email": email, "password": "password123"})
    token = signup.json()["access_token"]
    o = await client.post("/v1/orgs", json={"name": org}, headers={"Authorization": f"Bearer {token}"})
    return {"Authorization": f"Bearer {token}", "X-Org-Id": o.json()["id"]}


async def _agent(client: AsyncClient, headers: dict[str, str]) -> tuple[str, str]:
    agent = await client.post("/v1/agents", json={"name": "Camp Bot"}, headers=headers)
    return str(agent.json()["id"]), str(agent.json()["public_key"])


async def test_active_widget_campaign_reaches_the_public_config(client: AsyncClient) -> None:
    headers = await _headers(client, "camp1@example.com")
    aid, key = await _agent(client, headers)

    created = await client.post(
        "/v1/campaigns",
        json={
            "agent_id": aid,
            "kind": "widget_trigger",
            "name": "Pricing nudge",
            "message": "Questions about pricing? I can help.",
            "trigger_config": {"delay_seconds": 15, "url_pattern": "/pricing"},
            "status": "active",
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text

    config = await client.get(f"/v1/public/agents/{key}/config")
    assert config.status_code == 200
    campaigns = config.json()["campaigns"]
    assert len(campaigns) == 1
    assert campaigns[0]["message"] == "Questions about pricing? I can help."
    assert campaigns[0]["delay_seconds"] == 15
    assert campaigns[0]["url_pattern"] == "/pricing"


async def test_draft_and_paused_campaigns_stay_off_the_widget(client: AsyncClient) -> None:
    headers = await _headers(client, "camp2@example.com")
    aid, key = await _agent(client, headers)
    for status in ("draft", "paused"):
        await client.post(
            "/v1/campaigns",
            json={
                "agent_id": aid,
                "kind": "widget_trigger",
                "name": f"{status} one",
                "message": "hi",
                "status": status,
            },
            headers=headers,
        )
    config = await client.get(f"/v1/public/agents/{key}/config")
    assert config.json()["campaigns"] == []


async def test_broadcasts_cannot_be_activated(client: AsyncClient) -> None:
    """Consent, unsubscribe and rate-limited sending don't exist yet (ADR-039)."""
    headers = await _headers(client, "camp3@example.com")
    aid, _key = await _agent(client, headers)

    # The shape can be saved as a draft…
    draft = await client.post(
        "/v1/campaigns",
        json={
            "agent_id": aid,
            "kind": "broadcast",
            "name": "Spring sale",
            "message": "20% off",
            "status": "draft",
        },
        headers=headers,
    )
    assert draft.status_code == 201, draft.text

    # …but never switched on, at create time or later.
    at_create = await client.post(
        "/v1/campaigns",
        json={
            "agent_id": aid,
            "kind": "broadcast",
            "name": "Blast",
            "message": "hi",
            "status": "active",
        },
        headers=headers,
    )
    assert at_create.status_code == 422

    later = await client.patch(
        f"/v1/campaigns/{draft.json()['id']}", json={"status": "active"}, headers=headers
    )
    assert later.status_code == 400
    assert later.json()["error"]["code"] == "campaigns.broadcast_disabled"


async def test_broadcasts_never_reach_the_public_config(client: AsyncClient) -> None:
    headers = await _headers(client, "camp4@example.com")
    aid, key = await _agent(client, headers)
    await client.post(
        "/v1/campaigns",
        json={"agent_id": aid, "kind": "broadcast", "name": "Draft blast", "message": "x"},
        headers=headers,
    )
    assert (await client.get(f"/v1/public/agents/{key}/config")).json()["campaigns"] == []


async def test_delay_is_bounded(client: AsyncClient) -> None:
    """Firing on page load reads as a popup ad; an hour-plus delay never fires."""
    headers = await _headers(client, "camp5@example.com")
    aid, _key = await _agent(client, headers)
    for delay in (0, 99999):
        r = await client.post(
            "/v1/campaigns",
            json={
                "agent_id": aid,
                "kind": "widget_trigger",
                "name": "Bad delay",
                "message": "x",
                "trigger_config": {"delay_seconds": delay},
            },
            headers=headers,
        )
        assert r.status_code == 422, f"delay {delay} should be rejected"


async def test_tenant_isolation(client: AsyncClient) -> None:
    a = await _headers(client, "camp-a@example.com", org="OrgA")
    b = await _headers(client, "camp-b@example.com", org="OrgB")
    aid, _key = await _agent(client, a)
    created = await client.post(
        "/v1/campaigns",
        json={"agent_id": aid, "kind": "widget_trigger", "name": "Theirs", "message": "x"},
        headers=a,
    )
    assert (await client.get("/v1/campaigns", headers=b)).json() == []
    cross = await client.patch(
        f"/v1/campaigns/{created.json()['id']}", json={"name": "Mine"}, headers=b
    )
    assert cross.status_code == 404
