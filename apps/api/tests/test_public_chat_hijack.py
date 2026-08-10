"""Regression: a `conversation_id` was enough to read and post into a stranger's thread.

Found live as checklist item 12.3 in `docs/12-AGENT-TEST-CHECKLIST.md` (run 2026-08-09), and it
is worse than the "session resume on a shared device" the checklist describes.
`_get_or_create_conversation()` validated the conversation's agent, org and channel and never
checked **whose** it was, so any caller holding an id — leaked through browser history, a
screenshot, a pasted support link, a referrer header — got a 200, appended to the thread, and
had the whole prior transcript loaded into the model's history as context.

Reproduced against the live agent before the fix: posting as
`COMPLETELY-DIFFERENT-VISITOR-999` into a conversation owned by `qa-41a7b64c8b7b` was accepted
and the message landed between that visitor's own turns.

The other direction matters just as much: the widget sends an anonymous id it generates once
and keeps in `localStorage`, so a real visitor must still be able to continue their own chat.
"""

from __future__ import annotations

from httpx import AsyncClient

ALICE = {"id": "w-alice-device"}
MALLORY = {"id": "w-mallory-device"}


async def _public_key(client: AsyncClient, email: str) -> str:
    signup = await client.post("/v1/auth/signup", json={"email": email, "password": "password123"})
    token = signup.json()["access_token"]
    org = await client.post(
        "/v1/orgs", json={"name": "Hijack Org"}, headers={"Authorization": f"Bearer {token}"}
    )
    headers = {"Authorization": f"Bearer {token}", "X-Org-Id": org.json()["id"]}
    agent = await client.post("/v1/agents", json={"name": "Widget Bot"}, headers=headers)
    aid = agent.json()["id"]
    await client.patch(
        f"/v1/agents/{aid}/versions/1",
        json={"model_config": {"provider": "fake", "model": "fake-1"}},
        headers=headers,
    )
    return str(agent.json()["public_key"])


async def _start(client: AsyncClient, key: str, visitor: dict[str, str], message: str) -> str:
    r = await client.post(
        f"/v1/public/agents/{key}/chat",
        json={"message": message, "stream": False, "visitor": visitor},
    )
    assert r.status_code == 200, r.text
    return str(r.json()["conversation_id"])


async def test_another_visitor_cannot_post_into_someone_elses_conversation(
    client: AsyncClient,
) -> None:
    key = await _public_key(client, "hijack.deny@example.com")
    cid = await _start(client, key, ALICE, "my order number is 4471")

    stolen = await client.post(
        f"/v1/public/agents/{key}/chat",
        json={
            "message": "What did we talk about earlier in this chat?",
            "conversation_id": cid,
            "stream": False,
            "visitor": MALLORY,
        },
    )
    assert stolen.status_code == 404, stolen.text
    assert stolen.json()["error"]["code"] == "public.conversation_not_found"


async def test_the_owner_can_still_continue_their_own_conversation(client: AsyncClient) -> None:
    """The half that breaks if the check is written without the widget sending a stable id."""
    key = await _public_key(client, "hijack.allow@example.com")
    cid = await _start(client, key, ALICE, "my order number is 4471")

    again = await client.post(
        f"/v1/public/agents/{key}/chat",
        json={"message": "any update?", "conversation_id": cid, "stream": False, "visitor": ALICE},
    )
    assert again.status_code == 200, again.text
    assert again.json()["conversation_id"] == cid


async def test_a_stranger_gets_the_same_404_as_a_conversation_that_does_not_exist(
    client: AsyncClient,
) -> None:
    """No enumeration oracle: "not yours" and "no such thing" must be indistinguishable.

    A distinct status or error code would confirm that an id is live, which is exactly what an
    attacker holding a half-remembered id wants to know.
    """
    key = await _public_key(client, "hijack.oracle@example.com")
    cid = await _start(client, key, ALICE, "hello")

    stolen = await client.post(
        f"/v1/public/agents/{key}/chat",
        json={"message": "hi", "conversation_id": cid, "stream": False, "visitor": MALLORY},
    )
    imaginary = await client.post(
        f"/v1/public/agents/{key}/chat",
        json={
            "message": "hi",
            "conversation_id": "00000000-0000-4000-8000-000000000000",
            "stream": False,
            "visitor": MALLORY,
        },
    )
    assert stolen.status_code == imaginary.status_code == 404
    assert stolen.json() == imaginary.json()


async def test_an_anonymous_visitor_cannot_resume_by_omitting_the_visitor_field(
    client: AsyncClient,
) -> None:
    """Omitting `visitor` mints a fresh anonymous id, so it can never own an existing thread.

    This is the shape the pre-fix widget actually sent, and the reason the fix needed the
    widget change alongside it rather than on its own.
    """
    key = await _public_key(client, "hijack.anon@example.com")
    first = await client.post(
        f"/v1/public/agents/{key}/chat", json={"message": "one", "stream": False}
    )
    cid = first.json()["conversation_id"]

    second = await client.post(
        f"/v1/public/agents/{key}/chat",
        json={"message": "two", "conversation_id": cid, "stream": False},
    )
    assert second.status_code == 404


async def test_the_streaming_path_is_guarded_too(client: AsyncClient) -> None:
    """Both entry points share `_get_or_create_conversation`; assert it, don't assume it."""
    key = await _public_key(client, "hijack.stream@example.com")
    cid = await _start(client, key, ALICE, "hello")

    r = await client.post(
        f"/v1/public/agents/{key}/chat",
        json={"message": "hi", "conversation_id": cid, "stream": True, "visitor": MALLORY},
    )
    assert r.status_code == 404
