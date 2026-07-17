"""Phase 6: agents, versions, and the playground (real DB, tx-rollback)."""

from __future__ import annotations

import re

import pytest
from httpx import AsyncClient

from app.core.email import get_email_backend
from app.llm.fake import FakeChatProvider


async def _headers(client: AsyncClient, email: str = "a@example.com") -> tuple[dict[str, str], dict]:
    signup = await client.post("/v1/auth/signup", json={"email": email, "password": "password123"})
    token = signup.json()["access_token"]
    org = await client.post("/v1/orgs", json={"name": "Acme"}, headers={"Authorization": f"Bearer {token}"})
    org_json = org.json()
    return {"Authorization": f"Bearer {token}", "X-Org-Id": org_json["id"]}, org_json


async def _create_agent(client: AsyncClient, headers: dict[str, str], name: str = "Bot") -> dict:
    r = await client.post("/v1/agents", json={"name": name, "description": "d"}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


# ── CRUD ──────────────────────────────────────────────────────────────────────
async def test_create_list_get_agent(client: AsyncClient) -> None:
    headers, _ = await _headers(client)
    agent = await _create_agent(client, headers)
    assert agent["status"] == "draft"
    assert agent["public_key"].startswith("bf_pub_")
    assert agent["draft_version"] == 1
    assert agent["current_version_id"] is None

    listed = await client.get("/v1/agents", headers=headers)
    assert [a["id"] for a in listed.json()] == [agent["id"]]

    got = await client.get(f"/v1/agents/{agent['id']}", headers=headers)
    assert got.status_code == 200


async def test_update_and_delete_agent(client: AsyncClient) -> None:
    headers, _ = await _headers(client)
    agent = await _create_agent(client, headers)
    patched = await client.patch(
        f"/v1/agents/{agent['id']}", json={"name": "Renamed"}, headers=headers
    )
    assert patched.json()["name"] == "Renamed"

    assert (await client.delete(f"/v1/agents/{agent['id']}", headers=headers)).status_code == 204
    assert (await client.get(f"/v1/agents/{agent['id']}", headers=headers)).status_code == 404


async def test_duplicate_agent(client: AsyncClient) -> None:
    headers, _ = await _headers(client)
    agent = await _create_agent(client, headers, "Original")
    dup = await client.post(f"/v1/agents/{agent['id']}/duplicate", headers=headers)
    assert dup.status_code == 201
    assert dup.json()["name"] == "Original (copy)"
    assert dup.json()["id"] != agent["id"]


# ── Versions ──────────────────────────────────────────────────────────────────
async def test_version_lifecycle(client: AsyncClient) -> None:
    headers, _ = await _headers(client)
    agent = await _create_agent(client, headers)
    aid = agent["id"]

    # Patch draft v1 (note: JSON key is model_config, aliased server-side).
    patch = await client.patch(
        f"/v1/agents/{aid}/versions/1",
        json={
            "system_prompt": "You are helpful.",
            "welcome_message": "Hey!",
            "model_config": {"provider": "groq", "model": "llama-3.1-8b-instant", "temperature": 0.2},
        },
        headers=headers,
    )
    assert patch.status_code == 200
    assert patch.json()["system_prompt"] == "You are helpful."
    assert patch.json()["model_config"]["model"] == "llama-3.1-8b-instant"

    # Publish v1.
    published = await client.post(f"/v1/agents/{aid}/versions/1/publish", headers=headers)
    assert published.status_code == 200
    assert published.json()["status"] == "published"
    v1_current = published.json()["current_version_id"]
    assert v1_current is not None

    # Published versions are immutable.
    assert (
        await client.patch(f"/v1/agents/{aid}/versions/1", json={"system_prompt": "x"}, headers=headers)
    ).status_code == 409

    # New draft v2 copies from v1, edit + publish → current moves to v2.
    v2 = await client.post(f"/v1/agents/{aid}/versions", headers=headers)
    assert v2.json()["version"] == 2
    assert v2.json()["system_prompt"] == "You are helpful."  # copied
    await client.post(f"/v1/agents/{aid}/versions/2/publish", headers=headers)

    agent_now = (await client.get(f"/v1/agents/{aid}", headers=headers)).json()
    assert agent_now["current_version_id"] != v1_current

    # Roll back to v1.
    rolled = await client.post(f"/v1/agents/{aid}/rollback", json={"version": 1}, headers=headers)
    assert rolled.json()["current_version_id"] == v1_current

    versions = await client.get(f"/v1/agents/{aid}/versions", headers=headers)
    assert {v["version"] for v in versions.json()} == {1, 2}


# ── RBAC ──────────────────────────────────────────────────────────────────────
async def test_viewer_cannot_create_agent(client: AsyncClient) -> None:
    owner_headers, org = await _headers(client, "owner@example.com")
    invite = await client.post(
        f"/v1/orgs/{org['id']}/invitations", json={"email": "v@example.com", "role": "viewer"},
        headers=owner_headers,
    )
    assert invite.status_code == 201
    token = re.search(r"Token:\s*(\S+)", get_email_backend().outbox[-1].body).group(1)  # type: ignore[union-attr]
    signup = await client.post("/v1/auth/signup", json={"email": "v@example.com", "password": "password123"})
    viewer_token = signup.json()["access_token"]
    await client.post(f"/v1/orgs/invitations/{token}/accept", headers={"Authorization": f"Bearer {viewer_token}"})

    viewer_headers = {"Authorization": f"Bearer {viewer_token}", "X-Org-Id": org["id"]}
    r = await client.post("/v1/agents", json={"name": "Nope"}, headers=viewer_headers)
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "org.forbidden"


# ── Playground ────────────────────────────────────────────────────────────────
async def test_playground_streams(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.modules.agents import service

    async def _fake_provider(*_a: object, **_k: object) -> FakeChatProvider:
        return FakeChatProvider()

    monkeypatch.setattr(service, "get_chat_provider", _fake_provider)

    headers, _ = await _headers(client)
    agent = await _create_agent(client, headers)

    resp = await client.post(
        f"/v1/agents/{agent['id']}/playground/chat",
        json={"message": "hello there", "stream": True},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.text
    assert '"type":"token"' in body
    assert '"type":"done"' in body


async def test_playground_non_stream(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.modules.agents import service

    async def _fake_provider(*_a: object, **_k: object) -> FakeChatProvider:
        return FakeChatProvider()

    monkeypatch.setattr(service, "get_chat_provider", _fake_provider)

    headers, _ = await _headers(client)
    agent = await _create_agent(client, headers)
    resp = await client.post(
        f"/v1/agents/{agent['id']}/playground/chat",
        json={"message": "hi", "stream": False},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["content"] == "echo: hi"
