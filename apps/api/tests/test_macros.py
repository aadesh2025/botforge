"""Macros: CRUD, validation, and atomic execution against a conversation."""

from __future__ import annotations

import uuid

from httpx import AsyncClient


async def _headers(client: AsyncClient, email: str, org: str = "MacroOrg") -> dict[str, str]:
    signup = await client.post("/v1/auth/signup", json={"email": email, "password": "password123"})
    token = signup.json()["access_token"]
    o = await client.post("/v1/orgs", json={"name": org}, headers={"Authorization": f"Bearer {token}"})
    return {"Authorization": f"Bearer {token}", "X-Org-Id": o.json()["id"]}


async def _handed_off_conversation(client: AsyncClient, headers: dict[str, str]) -> str:
    """A widget conversation escalated to a human — what macros act on."""
    agent = await client.post("/v1/agents", json={"name": "Macro Bot"}, headers=headers)
    aid, key = agent.json()["id"], agent.json()["public_key"]
    await client.patch(
        f"/v1/agents/{aid}/versions/1",
        json={
            "fallback_message": "Connecting you to a teammate now.",
            "model_config": {"provider": "fake", "model": "fake-1"},
            "features": {"tools_enabled": False, "memory_enabled": True, "handoff_enabled": True},
        },
        headers=headers,
    )
    chat = await client.post(
        f"/v1/public/agents/{key}/chat", json={"message": "I want a human agent", "stream": False}
    )
    cid = chat.json()["conversation_id"]
    await client.post(f"/v1/inbox/conversations/{cid}/takeover", headers=headers)
    return str(cid)


async def _me(client: AsyncClient, headers: dict[str, str]) -> str:
    me = await client.get("/v1/auth/me", headers={"Authorization": headers["Authorization"]})
    return str(me.json()["user"]["id"])


async def test_crud_and_action_validation(client: AsyncClient) -> None:
    headers = await _headers(client, "mac1@example.com")

    created = await client.post(
        "/v1/macros",
        json={
            "name": "Refund and close",
            "actions": [
                {"type": "reply", "params": {"text": "Refunded — sorry about that."}},
                {"type": "add_tag", "params": {"tag": "refund"}},
                {"type": "resolve", "params": {}},
            ],
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    assert [a["type"] for a in created.json()["actions"]] == ["reply", "add_tag", "resolve"]

    listed = await client.get("/v1/macros", headers=headers)
    assert len(listed.json()) == 1

    renamed = await client.patch(
        f"/v1/macros/{created.json()['id']}", json={"name": "Refund"}, headers=headers
    )
    assert renamed.json()["name"] == "Refund"

    assert (
        await client.delete(f"/v1/macros/{created.json()['id']}", headers=headers)
    ).status_code == 204


async def test_half_formed_actions_are_rejected_at_save_time(client: AsyncClient) -> None:
    """Better to fail here than to discover it when an operator runs the macro."""
    headers = await _headers(client, "mac2@example.com")
    for bad in (
        {"type": "reply", "params": {}},  # no text, no canned response
        {"type": "add_tag", "params": {}},  # no tag
        {"type": "assign", "params": {}},  # no user
        {"type": "explode", "params": {}},  # not an action type at all
    ):
        r = await client.post("/v1/macros", json={"name": "Bad", "actions": [bad]}, headers=headers)
        assert r.status_code == 422, f"{bad} should be rejected: {r.text}"


async def test_run_applies_every_action_in_order(client: AsyncClient) -> None:
    headers = await _headers(client, "mac3@example.com")
    cid = await _handed_off_conversation(client, headers)
    uid = await _me(client, headers)

    macro = await client.post(
        "/v1/macros",
        json={
            "name": "Full sweep",
            "actions": [
                {"type": "reply", "params": {"text": "Sorted — anything else?"}},
                {"type": "add_tag", "params": {"tag": "billing"}},
                {"type": "assign", "params": {"user_id": uid}},
                {"type": "resolve", "params": {}},
            ],
        },
        headers=headers,
    )
    run = await client.post(
        f"/v1/inbox/conversations/{cid}/macros/{macro.json()['id']}", headers=headers
    )
    assert run.status_code == 200, run.text
    assert run.json()["applied"] == ["reply", "add_tag", "assign", "resolve"]

    detail = (await client.get(f"/v1/inbox/conversations/{cid}", headers=headers)).json()
    assert any(m["content"] == "Sorted — anything else?" for m in detail["messages"])
    assert detail["handoff"]["tags"] == ["billing"]
    assert detail["handoff"]["assigned_to"] == uid
    assert detail["status"] == "closed"


async def test_reply_can_use_a_canned_response(client: AsyncClient) -> None:
    headers = await _headers(client, "mac4@example.com")
    cid = await _handed_off_conversation(client, headers)
    canned = await client.post(
        "/v1/canned-responses",
        json={"shortcut": "refund", "content": "Your refund is on its way."},
        headers=headers,
    )
    macro = await client.post(
        "/v1/macros",
        json={
            "name": "Canned refund",
            "actions": [{"type": "reply", "params": {"canned_response_id": canned.json()["id"]}}],
        },
        headers=headers,
    )
    run = await client.post(
        f"/v1/inbox/conversations/{cid}/macros/{macro.json()['id']}", headers=headers
    )
    assert run.status_code == 200, run.text

    detail = (await client.get(f"/v1/inbox/conversations/{cid}", headers=headers)).json()
    assert any(m["content"] == "Your refund is on its way." for m in detail["messages"])


async def test_add_tag_preserves_existing_tags(client: AsyncClient) -> None:
    headers = await _headers(client, "mac5@example.com")
    cid = await _handed_off_conversation(client, headers)
    await client.post(
        f"/v1/inbox/conversations/{cid}/tags", json={"tags": ["urgent"]}, headers=headers
    )
    macro = await client.post(
        "/v1/macros",
        json={"name": "Tag", "actions": [{"type": "add_tag", "params": {"tag": "billing"}}]},
        headers=headers,
    )
    await client.post(f"/v1/inbox/conversations/{cid}/macros/{macro.json()['id']}", headers=headers)

    detail = (await client.get(f"/v1/inbox/conversations/{cid}", headers=headers)).json()
    assert sorted(detail["handoff"]["tags"]) == ["billing", "urgent"]

    # Running it again doesn't duplicate the tag.
    await client.post(f"/v1/inbox/conversations/{cid}/macros/{macro.json()['id']}", headers=headers)
    detail = (await client.get(f"/v1/inbox/conversations/{cid}", headers=headers)).json()
    assert detail["handoff"]["tags"].count("billing") == 1


async def test_a_broken_step_applies_nothing(client: AsyncClient) -> None:
    """Partial application — tagged but not replied — is confusing and hard to undo."""
    headers = await _headers(client, "mac6@example.com")
    cid = await _handed_off_conversation(client, headers)
    canned = await client.post(
        "/v1/canned-responses", json={"shortcut": "gone", "content": "bye"}, headers=headers
    )

    macro = await client.post(
        "/v1/macros",
        json={
            "name": "Tag then vanish",
            "actions": [
                {"type": "add_tag", "params": {"tag": "should-not-stick"}},
                {"type": "reply", "params": {"canned_response_id": canned.json()["id"]}},
            ],
        },
        headers=headers,
    )
    # Delete the canned response the macro depends on, out from under it.
    await client.delete(f"/v1/canned-responses/{canned.json()['id']}", headers=headers)

    run = await client.post(
        f"/v1/inbox/conversations/{cid}/macros/{macro.json()['id']}", headers=headers
    )
    assert run.status_code == 400
    assert run.json()["error"]["code"] == "macros.canned_response_missing"

    detail = (await client.get(f"/v1/inbox/conversations/{cid}", headers=headers)).json()
    assert detail["handoff"]["tags"] == [], "the tag from step 1 must not have stuck"


async def test_assigning_to_a_non_member_is_refused(client: AsyncClient) -> None:
    headers = await _headers(client, "mac7@example.com")
    cid = await _handed_off_conversation(client, headers)
    macro = await client.post(
        "/v1/macros",
        json={
            "name": "Assign stranger",
            "actions": [{"type": "assign", "params": {"user_id": str(uuid.uuid4())}}],
        },
        headers=headers,
    )
    run = await client.post(
        f"/v1/inbox/conversations/{cid}/macros/{macro.json()['id']}", headers=headers
    )
    assert run.status_code == 400
    assert run.json()["error"]["code"] == "macros.assignee_not_a_member"


async def test_tenant_isolation(client: AsyncClient) -> None:
    a = await _headers(client, "mac-a@example.com", org="OrgA")
    b = await _headers(client, "mac-b@example.com", org="OrgB")
    macro = await client.post(
        "/v1/macros",
        json={"name": "Theirs", "actions": [{"type": "resolve", "params": {}}]},
        headers=a,
    )
    assert (await client.get("/v1/macros", headers=b)).json() == []
    cross = await client.patch(
        f"/v1/macros/{macro.json()['id']}", json={"name": "Mine now"}, headers=b
    )
    assert cross.status_code == 404
