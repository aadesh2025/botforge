"""Phase 15 tests: API key issuance, masking, key-based auth, revocation."""

from __future__ import annotations

import re

from httpx import AsyncClient

from app.core.email import get_email_backend


async def _headers(client: AsyncClient, email: str = "ak@example.com") -> dict[str, str]:
    signup = await client.post("/v1/auth/signup", json={"email": email, "password": "password123"})
    token = signup.json()["access_token"]
    org = await client.post("/v1/orgs", json={"name": "AkOrg"}, headers={"Authorization": f"Bearer {token}"})
    return {"Authorization": f"Bearer {token}", "X-Org-Id": org.json()["id"]}


async def test_create_list_revoke_api_key(client: AsyncClient) -> None:
    headers = await _headers(client)
    created = await client.post("/v1/apikeys", json={"name": "CI key", "scopes": ["read"]}, headers=headers)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["key"].startswith("bf_")  # full key returned once
    assert body["key_prefix"] == body["key"][:12]

    listed = await client.get("/v1/apikeys", headers=headers)
    assert "key" not in listed.json()[0]  # never returned again
    assert listed.json()[0]["name"] == "CI key"

    revoked = await client.post(f"/v1/apikeys/{body['id']}/revoke", headers=headers)
    assert revoked.json()["revoked_at"] is not None


async def test_api_key_authenticates_requests(client: AsyncClient) -> None:
    headers = await _headers(client, "ak2@example.com")
    key = (await client.post("/v1/apikeys", json={"name": "prog"}, headers=headers)).json()["key"]

    # An API key authenticates org-scoped routes without a JWT or X-Org-Id.
    ok = await client.get("/v1/agents", headers={"X-API-Key": key})
    assert ok.status_code == 200, ok.text

    # Bearer bf_… also works.
    ok2 = await client.get("/v1/agents", headers={"Authorization": f"Bearer {key}"})
    assert ok2.status_code == 200

    # last_used_at is set after use.
    keys = await client.get("/v1/apikeys", headers=headers)
    assert keys.json()[0]["last_used_at"] is not None


async def test_revoked_and_invalid_keys_rejected(client: AsyncClient) -> None:
    headers = await _headers(client, "ak3@example.com")
    created = (await client.post("/v1/apikeys", json={"name": "temp"}, headers=headers)).json()
    key = created["key"]

    await client.post(f"/v1/apikeys/{created['id']}/revoke", headers=headers)
    assert (await client.get("/v1/agents", headers={"X-API-Key": key})).status_code == 401
    assert (await client.get("/v1/agents", headers={"X-API-Key": "bf_totally_invalid"})).status_code == 401


async def test_read_scoped_key_cannot_write(client: AsyncClient) -> None:
    headers = await _headers(client, "akscope@example.com")
    read_key = (
        await client.post("/v1/apikeys", json={"name": "ro", "scopes": ["read"]}, headers=headers)
    ).json()["key"]
    write_key = (
        await client.post("/v1/apikeys", json={"name": "rw", "scopes": ["write"]}, headers=headers)
    ).json()["key"]

    # Read scope: list (READ) works, create-agent (AGENTS_WRITE) is forbidden.
    assert (await client.get("/v1/agents", headers={"X-API-Key": read_key})).status_code == 200
    denied = await client.post("/v1/agents", json={"name": "X"}, headers={"X-API-Key": read_key})
    assert denied.status_code == 403, denied.text
    assert denied.json()["error"]["code"] == "org.forbidden"

    # Write scope: create-agent succeeds.
    ok = await client.post("/v1/agents", json={"name": "Y"}, headers={"X-API-Key": write_key})
    assert ok.status_code == 201, ok.text

    # A write-scoped key still cannot manage members: org-admin routes are JWT-only
    # (path-scoped org_context), so an API key is rejected there entirely — least privilege.
    org_id = headers["X-Org-Id"]
    forbidden = await client.post(
        f"/v1/orgs/{org_id}/invitations",
        json={"email": "nope@example.com", "role": "viewer"},
        headers={"X-API-Key": write_key},
    )
    assert forbidden.status_code in (401, 403)


async def test_viewer_cannot_create_api_key(client: AsyncClient) -> None:
    owner = await _headers(client, "akowner@example.com")
    org_id = owner["X-Org-Id"]
    invite = await client.post(
        f"/v1/orgs/{org_id}/invitations", json={"email": "akv@example.com", "role": "viewer"}, headers=owner
    )
    token = re.search(r"Token:\s*(\S+)", get_email_backend().outbox[-1].body).group(1)  # type: ignore[union-attr]
    signup = await client.post("/v1/auth/signup", json={"email": "akv@example.com", "password": "password123"})
    viewer_token = signup.json()["access_token"]
    await client.post(f"/v1/orgs/invitations/{token}/accept", headers={"Authorization": f"Bearer {viewer_token}"})
    assert invite.status_code == 201

    viewer = {"Authorization": f"Bearer {viewer_token}", "X-Org-Id": org_id}
    r = await client.post("/v1/apikeys", json={"name": "nope"}, headers=viewer)
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "org.forbidden"
