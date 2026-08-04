"""Handing an invited client their acceptance link directly.

The invitation email is queued automatically, but a fresh deployment ships
`EMAIL_BACKEND=console`, which delivers to nobody — so without this an admin can invite someone
and have no way to let them in.
"""

from __future__ import annotations

import datetime as dt

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import Invitation


def _auth(token: str, org_id: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if org_id:
        headers["X-Org-Id"] = org_id
    return headers


async def _signup(client: AsyncClient, email: str) -> str:
    r = await client.post("/v1/auth/signup", json={"email": email, "password": "password123"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


async def _org_with_invite(client: AsyncClient, email: str = "invitee@example.com") -> tuple[str, str, str]:
    owner = await _signup(client, "owner@example.com")
    org = (await client.post("/v1/orgs", json={"name": "Acme"}, headers=_auth(owner))).json()
    inv = await client.post(
        f"/v1/orgs/{org['id']}/invitations",
        json={"email": email, "role": "editor"},
        headers=_auth(owner),
    )
    assert inv.status_code == 201, inv.text
    return owner, org["id"], inv.json()["id"]


async def test_link_lets_the_invitee_join_without_any_email(client: AsyncClient) -> None:
    owner, org_id, inv_id = await _org_with_invite(client)

    link = await client.post(f"/v1/orgs/{org_id}/invitations/{inv_id}/link", headers=_auth(owner))
    assert link.status_code == 200, link.text
    url = link.json()["accept_url"]
    assert url.startswith(f"{settings.web_base_url}/invitations/accept?token=")

    # The invitee signs up with their own password and redeems the pasted link.
    token = url.split("token=", 1)[1]
    invitee = await _signup(client, "invitee@example.com")
    accept = await client.post(f"/v1/orgs/invitations/{token}/accept", headers=_auth(invitee))
    assert accept.status_code == 200, accept.text
    assert accept.json()["id"] == org_id


async def test_generating_a_link_invalidates_the_previous_one(client: AsyncClient) -> None:
    """Tokens are stored hashed, so a new link necessarily replaces the old one. The UI warns
    about this; the behaviour is pinned here so it cannot change silently."""
    owner, org_id, inv_id = await _org_with_invite(client)

    first = (await client.post(f"/v1/orgs/{org_id}/invitations/{inv_id}/link", headers=_auth(owner))).json()
    second = (await client.post(f"/v1/orgs/{org_id}/invitations/{inv_id}/link", headers=_auth(owner))).json()
    assert first["accept_url"] != second["accept_url"]

    invitee = await _signup(client, "invitee@example.com")
    stale = first["accept_url"].split("token=", 1)[1]
    rejected = await client.post(f"/v1/orgs/invitations/{stale}/accept", headers=_auth(invitee))
    assert rejected.status_code == 400
    assert rejected.json()["error"]["code"] == "org.invitation_invalid"

    fresh = second["accept_url"].split("token=", 1)[1]
    assert (await client.post(f"/v1/orgs/invitations/{fresh}/accept", headers=_auth(invitee))).status_code == 200


async def test_link_restarts_the_expiry_clock(client: AsyncClient, db_session: AsyncSession) -> None:
    owner, org_id, inv_id = await _org_with_invite(client)
    row = (await db_session.execute(select(Invitation).where(Invitation.id == inv_id))).scalar_one()
    row.expires_at = dt.datetime.now(tz=dt.UTC) + dt.timedelta(minutes=1)
    await db_session.flush()

    link = await client.post(f"/v1/orgs/{org_id}/invitations/{inv_id}/link", headers=_auth(owner))
    assert link.status_code == 200
    expires = dt.datetime.fromisoformat(link.json()["expires_at"])
    assert expires > dt.datetime.now(tz=dt.UTC) + dt.timedelta(days=6)


async def test_an_accepted_invitation_has_no_link_to_issue(client: AsyncClient) -> None:
    """Otherwise a revoked or spent invitation could be reopened from the members screen."""
    owner, org_id, inv_id = await _org_with_invite(client)
    url = (
        await client.post(f"/v1/orgs/{org_id}/invitations/{inv_id}/link", headers=_auth(owner))
    ).json()["accept_url"]
    invitee = await _signup(client, "invitee@example.com")
    await client.post(f"/v1/orgs/invitations/{url.split('token=', 1)[1]}/accept", headers=_auth(invitee))

    again = await client.post(f"/v1/orgs/{org_id}/invitations/{inv_id}/link", headers=_auth(owner))
    assert again.status_code == 404
    assert again.json()["error"]["code"] == "org.invitation_not_found"


async def test_a_member_without_members_manage_cannot_issue_a_link(client: AsyncClient) -> None:
    owner, org_id, inv_id = await _org_with_invite(client, email="editor@example.com")
    url = (
        await client.post(f"/v1/orgs/{org_id}/invitations/{inv_id}/link", headers=_auth(owner))
    ).json()["accept_url"]
    editor = await _signup(client, "editor@example.com")
    await client.post(f"/v1/orgs/invitations/{url.split('token=', 1)[1]}/accept", headers=_auth(editor))

    # An `editor` runs the agent but does not administer the workspace.
    second = await client.post(
        f"/v1/orgs/{org_id}/invitations", json={"email": "x@example.com", "role": "viewer"},
        headers=_auth(owner),
    )
    denied = await client.post(
        f"/v1/orgs/{org_id}/invitations/{second.json()['id']}/link",
        headers=_auth(editor, org_id),
    )
    assert denied.status_code == 403


async def test_an_invitation_from_another_org_is_not_found(client: AsyncClient) -> None:
    """Tenant isolation: knowing an invitation id must not be enough to mint a link for it."""
    _owner, _org_id, inv_id = await _org_with_invite(client)
    outsider = await _signup(client, "outsider@example.com")
    other = (await client.post("/v1/orgs", json={"name": "Other"}, headers=_auth(outsider))).json()

    resp = await client.post(
        f"/v1/orgs/{other['id']}/invitations/{inv_id}/link", headers=_auth(outsider)
    )
    assert resp.status_code == 404
