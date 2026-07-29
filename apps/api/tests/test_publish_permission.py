"""Editing a draft and publishing it are separate permissions.

A client shapes and tests their own agent freely; putting it in front of customers stays a
staff decision. The draft/publish machinery itself (branch-on-edit, `_live_version`) is
unchanged — only who may pull the trigger.
"""

from __future__ import annotations

import re

from httpx import AsyncClient

from app.core import rbac
from app.core.email import get_email_backend


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _signup(client: AsyncClient, email: str) -> str:
    r = await client.post("/v1/auth/signup", json={"email": email, "password": "password123"})
    assert r.status_code == 200, r.text
    return str(r.json()["access_token"])


def _last_token() -> str:
    body = get_email_backend().outbox[-1].body
    m = re.search(r"Token:\s*(\S+)", body)
    assert m, body
    return m.group(1)


async def _org_with_client(client: AsyncClient, prefix: str) -> tuple[dict[str, str], dict[str, str], str]:
    """An owner and an `editor`-role client in the same org, plus an agent id."""
    owner_token = await _signup(client, f"{prefix}-owner@example.com")
    org = await client.post("/v1/orgs", json={"name": "PubOrg"}, headers=_auth(owner_token))
    org_id = org.json()["id"]
    owner = {**_auth(owner_token), "X-Org-Id": org_id}

    invite = await client.post(
        f"/v1/orgs/{org_id}/invitations",
        json={"email": f"{prefix}-client@example.com", "role": "editor"},
        headers=owner,
    )
    assert invite.status_code == 201, invite.text
    token = _last_token()
    client_token = await _signup(client, f"{prefix}-client@example.com")
    accepted = await client.post(f"/v1/orgs/invitations/{token}/accept", headers=_auth(client_token))
    assert accepted.status_code == 200, accepted.text
    client_headers = {**_auth(client_token), "X-Org-Id": org_id}

    agent = await client.post("/v1/agents", json={"name": "Shared Bot"}, headers=owner)
    return owner, client_headers, str(agent.json()["id"])


def test_the_matrix_separates_the_two() -> None:
    for role in ("owner", "admin"):
        assert rbac.has_permission(role, rbac.AGENTS_PUBLISH)
    # The client role can edit, but not publish.
    assert rbac.has_permission("editor", rbac.AGENTS_WRITE)
    assert not rbac.has_permission("editor", rbac.AGENTS_PUBLISH)
    # …and keeps the things that are genuinely theirs.
    assert rbac.has_permission("editor", rbac.TOOLS_MANAGE)  # their own Meta credentials
    assert rbac.has_permission("editor", rbac.KB_MANAGE)


async def test_a_client_can_edit_a_draft_but_not_publish_it(client: AsyncClient) -> None:
    _owner, client_headers, agent_id = await _org_with_client(client, "split")

    edit = await client.patch(
        f"/v1/agents/{agent_id}/versions/1",
        json={"system_prompt": "Be concise."},
        headers=client_headers,
    )
    assert edit.status_code == 200, edit.text

    blocked = await client.post(f"/v1/agents/{agent_id}/versions/1/publish", headers=client_headers)
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "org.forbidden"


async def test_a_client_can_use_the_playground(client: AsyncClient) -> None:
    """Testing what they built is the whole point of letting them edit."""
    _owner, client_headers, agent_id = await _org_with_client(client, "play")
    await client.patch(
        f"/v1/agents/{agent_id}/versions/1",
        json={"model_config": {"provider": "fake", "model": "fake-1"}},
        headers=client_headers,
    )
    r = await client.post(
        f"/v1/agents/{agent_id}/chat", json={"message": "hello", "stream": False}, headers=client_headers
    )
    assert r.status_code == 200, r.text


async def test_a_client_cannot_roll_back_either(client: AsyncClient) -> None:
    owner, client_headers, agent_id = await _org_with_client(client, "roll")
    published = await client.post(f"/v1/agents/{agent_id}/versions/1/publish", headers=owner)
    assert published.status_code == 200, published.text

    blocked = await client.post(
        f"/v1/agents/{agent_id}/rollback", json={"version": 1}, headers=client_headers
    )
    assert blocked.status_code == 403


async def test_staff_side_publishing_still_works(client: AsyncClient) -> None:
    owner, client_headers, agent_id = await _org_with_client(client, "flow")

    # The client edits a published agent — branch-on-edit forks a new draft.
    await client.post(f"/v1/agents/{agent_id}/versions/1/publish", headers=owner)
    edited = await client.patch(
        f"/v1/agents/{agent_id}/versions/1", json={"system_prompt": "Client wording."}, headers=client_headers
    )
    assert edited.status_code == 200, edited.text
    new_version = edited.json()["version"]
    assert new_version == 2, "editing a published version should fork a draft"

    # …and the owner publishes it for them.
    ok = await client.post(f"/v1/agents/{agent_id}/versions/{new_version}/publish", headers=owner)
    assert ok.status_code == 200, ok.text


async def test_admin_console_counts_agents_awaiting_review(
    client: AsyncClient, db_session  # type: ignore[no-untyped-def]
) -> None:
    """Clients can save but not publish, so staff need a signal that work is waiting."""
    from sqlalchemy import select

    from app.models import User

    owner, client_headers, agent_id = await _org_with_client(client, "admin-count")

    staff_token = await _signup(client, "pub-staff@example.com")
    user = (
        await db_session.execute(select(User).where(User.email == "pub-staff@example.com"))
    ).scalar_one()
    user.is_staff = True
    await db_session.flush()

    def _row(orgs: list[dict]) -> dict:
        return next(o for o in orgs if o["name"] == "PubOrg")

    # Never published → already counts as waiting.
    orgs = (await client.get("/v1/admin/orgs", headers=_auth(staff_token))).json()
    assert _row(orgs)["agents_with_unpublished_changes"] == 1

    await client.post(f"/v1/agents/{agent_id}/versions/1/publish", headers=owner)
    orgs = (await client.get("/v1/admin/orgs", headers=_auth(staff_token))).json()
    assert _row(orgs)["agents_with_unpublished_changes"] == 0, "nothing is waiting once live"

    # The client edits again → back to waiting.
    await client.patch(
        f"/v1/agents/{agent_id}/versions/1", json={"system_prompt": "Another tweak."}, headers=client_headers
    )
    orgs = (await client.get("/v1/admin/orgs", headers=_auth(staff_token))).json()
    assert _row(orgs)["agents_with_unpublished_changes"] == 1
