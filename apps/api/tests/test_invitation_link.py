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


async def test_preview_tells_the_page_which_org_and_whether_to_offer_sign_in(
    client: AsyncClient,
) -> None:
    """Without this the page defaults to signup, and anyone who already has an account walks
    into `auth.email_taken` with no way forward."""
    owner, org_id, inv_id = await _org_with_invite(client)
    url = (
        await client.post(f"/v1/orgs/{org_id}/invitations/{inv_id}/link", headers=_auth(owner))
    ).json()["accept_url"]
    token = url.split("token=", 1)[1]

    # Unauthenticated: the invitee has no session yet.
    resp = await client.get(f"/v1/orgs/invitations/{token}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["organization_name"] == "Acme"
    assert body["role"] == "editor"
    assert body["email"] == "invitee@example.com"
    assert body["account_exists"] is False

    # Once that address has an account, the page must offer sign-in instead.
    await _signup(client, "invitee@example.com")
    again = await client.get(f"/v1/orgs/invitations/{token}")
    assert again.json()["account_exists"] is True


async def test_preview_of_a_spent_invitation_is_indistinguishable_from_a_bad_token(
    client: AsyncClient,
) -> None:
    owner, org_id, inv_id = await _org_with_invite(client)
    url = (
        await client.post(f"/v1/orgs/{org_id}/invitations/{inv_id}/link", headers=_auth(owner))
    ).json()["accept_url"]
    token = url.split("token=", 1)[1]
    invitee = await _signup(client, "invitee@example.com")
    await client.post(f"/v1/orgs/invitations/{token}/accept", headers=_auth(invitee))

    spent = await client.get(f"/v1/orgs/invitations/{token}")
    invented = await client.get("/v1/orgs/invitations/not-a-real-token")
    assert spent.status_code == invented.status_code == 400
    assert spent.json()["error"]["code"] == invented.json()["error"]["code"] == "org.invitation_invalid"


async def test_an_existing_user_can_join_a_second_org_and_keep_the_first(
    client: AsyncClient,
) -> None:
    """The whole point: an account already belonging to one org joins another by invitation and
    ends up able to switch between them."""
    first_owner = await _signup(client, "first@example.com")
    first = (await client.post("/v1/orgs", json={"name": "First"}, headers=_auth(first_owner))).json()
    # The invitee already has an account and an org of their own.
    member = await _signup(client, "member@example.com")
    await client.post("/v1/orgs", json={"name": "Own"}, headers=_auth(member))

    inv = await client.post(
        f"/v1/orgs/{first['id']}/invitations",
        json={"email": "member@example.com", "role": "editor"},
        headers=_auth(first_owner),
    )
    assert inv.status_code == 201, inv.text
    assert inv.json()["account_exists"] is True

    url = (
        await client.post(
            f"/v1/orgs/{first['id']}/invitations/{inv.json()['id']}/link", headers=_auth(first_owner)
        )
    ).json()["accept_url"]
    joined = await client.post(
        f"/v1/orgs/invitations/{url.split('token=', 1)[1]}/accept", headers=_auth(member)
    )
    assert joined.status_code == 200, joined.text

    orgs = (await client.get("/v1/orgs", headers=_auth(member))).json()
    assert {o["name"] for o in orgs} == {"Own", "First"}
    assert next(o for o in orgs if o["name"] == "First")["role"] == "editor"
    assert next(o for o in orgs if o["name"] == "Own")["role"] == "owner"


async def test_pending_invitations_flag_addresses_that_already_have_accounts(
    client: AsyncClient,
) -> None:
    owner, org_id, _inv_id = await _org_with_invite(client, email="known@example.com")
    await _signup(client, "known@example.com")
    await client.post(
        f"/v1/orgs/{org_id}/invitations", json={"email": "stranger@example.com", "role": "viewer"},
        headers=_auth(owner),
    )

    listed = (await client.get(f"/v1/orgs/{org_id}/invitations", headers=_auth(owner))).json()
    by_email = {i["email"]: i["account_exists"] for i in listed}
    assert by_email == {"known@example.com": True, "stranger@example.com": False}


async def test_an_invitation_from_another_org_is_not_found(client: AsyncClient) -> None:
    """Tenant isolation: knowing an invitation id must not be enough to mint a link for it."""
    _owner, _org_id, inv_id = await _org_with_invite(client)
    outsider = await _signup(client, "outsider@example.com")
    other = (await client.post("/v1/orgs", json={"name": "Other"}, headers=_auth(outsider))).json()

    resp = await client.post(
        f"/v1/orgs/{other['id']}/invitations/{inv_id}/link", headers=_auth(outsider)
    )
    assert resp.status_code == 404
