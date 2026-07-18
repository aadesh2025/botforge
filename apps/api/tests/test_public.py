"""Phase 11 tests: public widget config + public chat (no dashboard auth)."""

from __future__ import annotations

from httpx import AsyncClient


async def _agent_with_key(client: AsyncClient, email: str = "pub@example.com") -> tuple[str, dict[str, str]]:
    signup = await client.post("/v1/auth/signup", json={"email": email, "password": "password123"})
    token = signup.json()["access_token"]
    org = await client.post("/v1/orgs", json={"name": "PubOrg"}, headers={"Authorization": f"Bearer {token}"})
    headers = {"Authorization": f"Bearer {token}", "X-Org-Id": org.json()["id"]}
    agent = await client.post("/v1/agents", json={"name": "Widget Bot"}, headers=headers)
    aid = agent.json()["id"]
    # Deterministic fake provider + a widget theme + welcome/prompts.
    await client.patch(
        f"/v1/agents/{aid}/versions/1",
        json={
            "welcome_message": "Hey there 👋",
            "suggested_prompts": ["What are your hours?"],
            "model_config": {"provider": "fake", "model": "fake-1"},
            "persona": {"displayName": "Aiko", "widget": {"primaryColor": "#123456", "position": "bottom-left"}},
        },
        headers=headers,
    )
    return agent.json()["public_key"], headers


async def test_public_config(client: AsyncClient) -> None:
    public_key, _ = await _agent_with_key(client)
    r = await client.get(f"/v1/public/agents/{public_key}/config")  # no auth headers
    assert r.status_code == 200, r.text
    cfg = r.json()
    assert cfg["name"] == "Aiko"
    assert cfg["welcome_message"] == "Hey there 👋"
    assert cfg["suggested_prompts"] == ["What are your hours?"]
    assert cfg["theme"]["primary_color"] == "#123456"
    assert cfg["theme"]["position"] == "bottom-left"


async def test_public_config_unknown_key_404(client: AsyncClient) -> None:
    r = await client.get("/v1/public/agents/bf_pub_nope/config")
    assert r.status_code == 404


async def test_public_chat_stream_no_auth(client: AsyncClient) -> None:
    public_key, _ = await _agent_with_key(client, "pub2@example.com")
    r = await client.post(
        f"/v1/public/agents/{public_key}/chat",
        json={"message": "hello widget", "stream": True, "visitor": {"id": "v1", "name": "Sam"}},
    )
    assert r.status_code == 200, r.text
    body = r.text
    assert '"type":"conversation"' in body
    assert '"type":"token"' in body
    assert '"type":"message"' in body


async def test_public_chat_persists_and_continues(client: AsyncClient) -> None:
    public_key, headers = await _agent_with_key(client, "pub3@example.com")
    first = await client.post(
        f"/v1/public/agents/{public_key}/chat", json={"message": "one", "stream": False}
    )
    data = first.json()
    assert data["content"] == "echo: one"
    cid = data["conversation_id"]

    second = await client.post(
        f"/v1/public/agents/{public_key}/chat",
        json={"message": "two", "conversation_id": cid, "stream": False},
    )
    assert second.json()["conversation_id"] == cid

    # The widget conversation is visible in the dashboard (same org) with channel "widget".
    convs = await client.get("/v1/conversations", headers=headers)
    widget_convs = [c for c in convs.json() if c["channel"] == "widget"]
    assert widget_convs and widget_convs[0]["message_count"] == 4
