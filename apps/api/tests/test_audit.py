"""Phase 15 tests: audit log endpoint + sensitive-mutation recording + RBAC."""

from __future__ import annotations

import re

from httpx import AsyncClient

from app.core.email import get_email_backend


async def _headers(client: AsyncClient, email: str = "au@example.com") -> dict[str, str]:
    signup = await client.post("/v1/auth/signup", json={"email": email, "password": "password123"})
    token = signup.json()["access_token"]
    org = await client.post("/v1/orgs", json={"name": "AuOrg"}, headers={"Authorization": f"Bearer {token}"})
    return {"Authorization": f"Bearer {token}", "X-Org-Id": org.json()["id"]}


async def test_sensitive_mutations_are_audited(client: AsyncClient) -> None:
    headers = await _headers(client)
    # Creating an API key + a webhook are sensitive mutations.
    await client.post("/v1/apikeys", json={"name": "k"}, headers=headers)
    await client.post("/v1/webhooks", json={"url": "https://example.com/h", "events": ["*"]}, headers=headers)

    audit = await client.get("/v1/audit", headers=headers)
    assert audit.status_code == 200, audit.text
    actions = {e["action"] for e in audit.json()}
    assert "apikey.created" in actions
    assert "webhook.created" in actions
    assert "org.created" in actions  # from org creation


async def test_audit_filter_by_action(client: AsyncClient) -> None:
    headers = await _headers(client, "au2@example.com")
    key = (await client.post("/v1/apikeys", json={"name": "k"}, headers=headers)).json()
    await client.post(f"/v1/apikeys/{key['id']}/revoke", headers=headers)

    filtered = await client.get("/v1/audit?action=apikey.revoked", headers=headers)
    assert filtered.json() and all(e["action"] == "apikey.revoked" for e in filtered.json())
    assert filtered.json()[0]["target_id"] == key["id"]


async def test_viewer_cannot_read_audit(client: AsyncClient) -> None:
    owner = await _headers(client, "auowner@example.com")
    org_id = owner["X-Org-Id"]
    await client.post(
        f"/v1/orgs/{org_id}/invitations", json={"email": "auv@example.com", "role": "viewer"}, headers=owner
    )
    token = re.search(r"Token:\s*(\S+)", get_email_backend().outbox[-1].body).group(1)  # type: ignore[union-attr]
    signup = await client.post("/v1/auth/signup", json={"email": "auv@example.com", "password": "password123"})
    viewer_token = signup.json()["access_token"]
    await client.post(f"/v1/orgs/invitations/{token}/accept", headers={"Authorization": f"Bearer {viewer_token}"})

    viewer = {"Authorization": f"Bearer {viewer_token}", "X-Org-Id": org_id}
    r = await client.get("/v1/audit", headers=viewer)
    assert r.status_code == 403  # only admins/owners can read the audit log
