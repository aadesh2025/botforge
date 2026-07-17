"""Phase 3: organizations, membership, invitations, and RBAC (real DB, tx-rollback)."""

from __future__ import annotations

import re
import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.email import get_email_backend
from app.modules.orgs import service


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _last_token() -> str:
    body = get_email_backend().outbox[-1].body
    m = re.search(r"Token:\s*(\S+)", body)
    assert m, body
    return m.group(1)


async def _signup(client: AsyncClient, email: str) -> str:
    r = await client.post("/v1/auth/signup", json={"email": email, "password": "password123"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


async def _create_org(client: AsyncClient, token: str, name: str = "Acme") -> dict:
    r = await client.post("/v1/orgs", json={"name": name}, headers=_auth(token))
    assert r.status_code == 201, r.text
    return r.json()


async def _user_id(client: AsyncClient, token: str) -> str:
    r = await client.get("/v1/auth/me", headers=_auth(token))
    return r.json()["user"]["id"]


async def _invite_and_join(
    client: AsyncClient, owner_token: str, org_id: str, email: str, role: str = "editor"
) -> str:
    inv = await client.post(
        f"/v1/orgs/{org_id}/invitations", json={"email": email, "role": role}, headers=_auth(owner_token)
    )
    assert inv.status_code == 201, inv.text
    token = _last_token()  # capture before the invitee's signup adds a verification email
    invitee = await _signup(client, email)
    accept = await client.post(f"/v1/orgs/invitations/{token}/accept", headers=_auth(invitee))
    assert accept.status_code == 200, accept.text
    return invitee


# ── Org CRUD & isolation ──────────────────────────────────────────────────────
async def test_create_list_get_org(client: AsyncClient) -> None:
    token = await _signup(client, "a@example.com")
    org = await _create_org(client, token)
    assert org["role"] == "owner"
    assert org["slug"] == "acme"

    listed = await client.get("/v1/orgs", headers=_auth(token))
    assert [o["id"] for o in listed.json()] == [org["id"]]

    me = await client.get("/v1/auth/me", headers=_auth(token))
    assert len(me.json()["memberships"]) == 1
    assert me.json()["memberships"][0]["role"] == "owner"


async def test_slug_uniqueness(client: AsyncClient) -> None:
    token = await _signup(client, "a@example.com")
    first = await _create_org(client, token, "Acme")
    second = await _create_org(client, token, "Acme")
    assert first["slug"] == "acme"
    assert second["slug"] == "acme-2"


async def test_non_member_forbidden(client: AsyncClient) -> None:
    owner = await _signup(client, "a@example.com")
    org = await _create_org(client, owner)
    outsider = await _signup(client, "b@example.com")
    r = await client.get(f"/v1/orgs/{org['id']}", headers=_auth(outsider))
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "org.forbidden"


async def test_delete_org_then_404(client: AsyncClient) -> None:
    token = await _signup(client, "a@example.com")
    org = await _create_org(client, token)
    assert (await client.delete(f"/v1/orgs/{org['id']}", headers=_auth(token))).status_code == 204
    assert (await client.get(f"/v1/orgs/{org['id']}", headers=_auth(token))).status_code == 404


# ── Invitations ───────────────────────────────────────────────────────────────
async def test_invite_accept_flow(client: AsyncClient) -> None:
    owner = await _signup(client, "a@example.com")
    org = await _create_org(client, owner)
    invitee = await _invite_and_join(client, owner, org["id"], "b@example.com", "editor")

    members = await client.get(f"/v1/orgs/{org['id']}/members", headers=_auth(owner))
    assert {m["email"] for m in members.json()} == {"a@example.com", "b@example.com"}

    me_b = await client.get("/v1/auth/me", headers=_auth(invitee))
    assert me_b.json()["memberships"][0]["role"] == "editor"


async def test_invite_email_mismatch(client: AsyncClient) -> None:
    owner = await _signup(client, "a@example.com")
    org = await _create_org(client, owner)
    await client.post(
        f"/v1/orgs/{org['id']}/invitations", json={"email": "b@example.com", "role": "editor"},
        headers=_auth(owner),
    )
    token = _last_token()
    wrong = await _signup(client, "someone-else@example.com")
    r = await client.post(f"/v1/orgs/invitations/{token}/accept", headers=_auth(wrong))
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "org.invite_email_mismatch"


# ── RBAC ──────────────────────────────────────────────────────────────────────
async def test_editor_cannot_manage(client: AsyncClient) -> None:
    owner = await _signup(client, "a@example.com")
    org = await _create_org(client, owner)
    editor = await _invite_and_join(client, owner, org["id"], "b@example.com", "editor")

    # Editor can read.
    assert (await client.get(f"/v1/orgs/{org['id']}", headers=_auth(editor))).status_code == 200
    # But cannot update the org, invite, or delete.
    assert (await client.patch(f"/v1/orgs/{org['id']}", json={"name": "X"}, headers=_auth(editor))).status_code == 403
    inv = await client.post(
        f"/v1/orgs/{org['id']}/invitations", json={"email": "c@example.com", "role": "viewer"},
        headers=_auth(editor),
    )
    assert inv.status_code == 403
    assert (await client.delete(f"/v1/orgs/{org['id']}", headers=_auth(editor))).status_code == 403


async def test_admin_can_invite_but_not_delete_org(client: AsyncClient) -> None:
    owner = await _signup(client, "a@example.com")
    org = await _create_org(client, owner)
    admin = await _invite_and_join(client, owner, org["id"], "b@example.com", "admin")

    ok = await client.post(
        f"/v1/orgs/{org['id']}/invitations", json={"email": "c@example.com", "role": "viewer"},
        headers=_auth(admin),
    )
    assert ok.status_code == 201  # admin can invite
    # But org management (delete) is owner-only.
    assert (await client.delete(f"/v1/orgs/{org['id']}", headers=_auth(admin))).status_code == 403


async def test_change_role_and_remove_member(client: AsyncClient) -> None:
    owner = await _signup(client, "a@example.com")
    org = await _create_org(client, owner)
    member = await _invite_and_join(client, owner, org["id"], "b@example.com", "editor")
    member_id = await _user_id(client, member)

    promote = await client.patch(
        f"/v1/orgs/{org['id']}/members/{member_id}", json={"role": "admin"}, headers=_auth(owner)
    )
    assert promote.status_code == 200
    # Now the member (admin) can invite.
    assert (
        await client.post(
            f"/v1/orgs/{org['id']}/invitations", json={"email": "c@example.com", "role": "viewer"},
            headers=_auth(member),
        )
    ).status_code == 201

    remove = await client.delete(f"/v1/orgs/{org['id']}/members/{member_id}", headers=_auth(owner))
    assert remove.status_code == 204
    # Removed member loses access.
    assert (await client.get("/v1/orgs", headers=_auth(member))).json() == []


async def test_transfer_ownership(client: AsyncClient) -> None:
    owner = await _signup(client, "a@example.com")
    org = await _create_org(client, owner)
    other = await _invite_and_join(client, owner, org["id"], "b@example.com", "admin")
    other_id = await _user_id(client, other)

    transfer = await client.post(
        f"/v1/orgs/{org['id']}/transfer-ownership", json={"user_id": other_id}, headers=_auth(owner)
    )
    assert transfer.status_code == 200

    # New owner can delete; the former owner (now admin) cannot.
    assert (await client.delete(f"/v1/orgs/{org['id']}", headers=_auth(owner))).status_code == 403
    assert (await client.delete(f"/v1/orgs/{org['id']}", headers=_auth(other))).status_code == 204


async def test_cannot_change_owner_role(client: AsyncClient) -> None:
    owner = await _signup(client, "a@example.com")
    org = await _create_org(client, owner)
    owner_id = await _user_id(client, owner)
    r = await client.patch(
        f"/v1/orgs/{org['id']}/members/{owner_id}", json={"role": "admin"}, headers=_auth(owner)
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "org.cannot_change_owner"


# ── Audit ─────────────────────────────────────────────────────────────────────
async def test_audit_written_on_mutations(client: AsyncClient, db_session: AsyncSession) -> None:
    owner = await _signup(client, "a@example.com")
    org = await _create_org(client, owner)
    await client.patch(f"/v1/orgs/{org['id']}", json={"name": "Renamed"}, headers=_auth(owner))
    count = await service.audit_count(db_session, uuid.UUID(org["id"]))
    assert count >= 2  # org.created + org.updated
