"""Creating an *additional* organization is staff-only.

BotForge is run as one organization per client, provisioned for them — not as a self-serve
product where anyone spins up as many as they like. The first org is always allowed
(signup's create-first-org step comes through the same endpoint), every later one needs
`is_staff`. Enforced server-side: hiding the button doesn't stop a direct API call.
"""

from __future__ import annotations

import re

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.email import get_email_backend
from app.models import User


def _last_invite_token() -> str:
    body = get_email_backend().outbox[-1].body
    m = re.search(r"Token:\s*(\S+)", body)
    assert m, body
    return m.group(1)


async def _signup(client: AsyncClient, email: str) -> str:
    r = await client.post("/v1/auth/signup", json={"email": email, "password": "password123"})
    assert r.status_code == 200, r.text
    return str(r.json()["access_token"])


async def _make_staff(db_session: AsyncSession, email: str) -> None:
    user = (await db_session.execute(select(User).where(User.email == email))).scalar_one()
    user.is_staff = True
    await db_session.flush()


async def test_a_brand_new_user_can_create_their_first_org(client: AsyncClient) -> None:
    """The signup flow's create-first-org step — a new user obviously isn't staff yet."""
    token = await _signup(client, "first@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    created = await client.post("/v1/orgs", json={"name": "My Company"}, headers=headers)
    assert created.status_code == 201, created.text
    assert created.json()["name"] == "My Company"


async def test_a_client_cannot_create_a_second_org(client: AsyncClient) -> None:
    token = await _signup(client, "client@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    assert (await client.post("/v1/orgs", json={"name": "Theirs"}, headers=headers)).status_code == 201

    second = await client.post("/v1/orgs", json={"name": "Sneaky Extra"}, headers=headers)
    assert second.status_code == 403, second.text
    assert second.json()["error"]["code"] == "orgs.create_forbidden"

    # And nothing was created behind the refusal.
    assert len((await client.get("/v1/orgs", headers=headers)).json()) == 1


async def test_staff_can_create_as_many_as_they_need(client: AsyncClient, db_session: AsyncSession) -> None:
    token = await _signup(client, "staff-orgs@example.com")
    await _make_staff(db_session, "staff-orgs@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    for name in ("Client A", "Client B", "Client C"):
        r = await client.post("/v1/orgs", json={"name": name}, headers=headers)
        assert r.status_code == 201, f"{name}: {r.text}"

    assert len((await client.get("/v1/orgs", headers=headers)).json()) == 3


async def test_an_invited_member_cannot_create_one_either(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Membership via invite still counts — the gate is "has an org", not "created one"."""
    owner_token = await _signup(client, "owner-gate@example.com")
    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    org = await client.post("/v1/orgs", json={"name": "Host Org"}, headers=owner_headers)
    org_id = org.json()["id"]

    invite = await client.post(
        f"/v1/orgs/{org_id}/invitations",
        json={"email": "invitee-gate@example.com", "role": "editor"},
        headers={**owner_headers, "X-Org-Id": org_id},
    )
    assert invite.status_code == 201, invite.text
    token = _last_invite_token()  # capture before signup adds a verification email

    invitee_token = await _signup(client, "invitee-gate@example.com")
    invitee_headers = {"Authorization": f"Bearer {invitee_token}"}
    accepted = await client.post(f"/v1/orgs/invitations/{token}/accept", headers=invitee_headers)
    assert accepted.status_code == 200, accepted.text

    # They now belong to an org they didn't create — still can't make another.
    blocked = await client.post("/v1/orgs", json={"name": "Mine"}, headers=invitee_headers)
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "orgs.create_forbidden"


async def test_deleting_your_only_org_lets_you_create_a_replacement(client: AsyncClient) -> None:
    """Otherwise deleting your last org would strand the account with no way back in."""
    token = await _signup(client, "recreate@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    org = await client.post("/v1/orgs", json={"name": "Temporary"}, headers=headers)
    org_id = org.json()["id"]

    gone = await client.delete(f"/v1/orgs/{org_id}", headers={**headers, "X-Org-Id": org_id})
    assert gone.status_code == 204, gone.text

    again = await client.post("/v1/orgs", json={"name": "Fresh Start"}, headers=headers)
    assert again.status_code == 201, again.text
