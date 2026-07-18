"""Phase 13 tests: handoff triggers, inbox queue, operator actions, bot pause/resume."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.llm.fake import ScriptedToolProvider
from app.llm.types import ToolCall
from app.main import create_app


async def _headers(client: AsyncClient, email: str = "inbox@example.com") -> dict[str, str]:
    signup = await client.post("/v1/auth/signup", json={"email": email, "password": "password123"})
    token = signup.json()["access_token"]
    org = await client.post("/v1/orgs", json={"name": "InboxOrg"}, headers={"Authorization": f"Bearer {token}"})
    return {"Authorization": f"Bearer {token}", "X-Org-Id": org.json()["id"]}


async def _handoff_agent(client: AsyncClient, headers: dict[str, str]) -> tuple[str, str]:
    agent = await client.post("/v1/agents", json={"name": "HO Bot"}, headers=headers)
    aid = agent.json()["id"]
    await client.patch(
        f"/v1/agents/{aid}/versions/1",
        json={
            "fallback_message": "Connecting you to a teammate now.",
            "model_config": {"provider": "fake", "model": "fake-1"},
            "features": {"tools_enabled": False, "memory_enabled": True, "handoff_enabled": True},
        },
        headers=headers,
    )
    return aid, agent.json()["public_key"]


async def _public_chat(client: AsyncClient, key: str, msg: str, cid: str | None = None) -> dict:
    body = {"message": msg, "stream": False}
    if cid:
        body["conversation_id"] = cid
    r = await client.post(f"/v1/public/agents/{key}/chat", json=body)
    assert r.status_code == 200, r.text
    return r.json()


# ── Keyword handoff pauses the bot ──────────────────────────────────────────────────
async def test_keyword_handoff_and_pause(client: AsyncClient) -> None:
    headers = await _headers(client)
    _aid, key = await _handoff_agent(client, headers)

    first = await _public_chat(client, key, "hello there")
    assert first["content"] == "echo: hello there"  # bot answers normally
    cid = first["conversation_id"]

    ho = await _public_chat(client, key, "can I talk to a human please?", cid)
    assert ho["content"] == "Connecting you to a teammate now."  # canned handoff message

    # Bot is now paused: further messages get no bot reply.
    paused = await _public_chat(client, key, "are you there?", cid)
    assert paused["content"] == ""

    # It shows up in the inbox queue.
    inbox = await client.get("/v1/inbox/conversations", headers=headers)
    assert inbox.status_code == 200, inbox.text
    items = inbox.json()
    assert any(i["id"] == cid and i["status"] == "handoff" for i in items)
    item = next(i for i in items if i["id"] == cid)
    assert item["handoff"]["requested_by"] == "user"


# ── Operator takeover → reply → handback resumes the bot ────────────────────────────
async def test_operator_takeover_reply_handback(client: AsyncClient) -> None:
    headers = await _headers(client, "op@example.com")
    _aid, key = await _handoff_agent(client, headers)
    cid = (await _public_chat(client, key, "I need a human agent"))["conversation_id"]

    take = await client.post(f"/v1/inbox/conversations/{cid}/takeover", headers=headers)
    assert take.status_code == 200
    assert take.json()["handoff"]["status"] == "assigned"

    reply = await client.post(
        f"/v1/inbox/conversations/{cid}/messages", json={"text": "Hi, I'm Sam. How can I help?"}, headers=headers
    )
    assert reply.status_code == 200
    assert reply.json()["provider"] == "operator"

    detail = await client.get(f"/v1/inbox/conversations/{cid}", headers=headers)
    op_msgs = [m for m in detail.json()["messages"] if m["provider"] == "operator"]
    assert op_msgs and op_msgs[-1]["content"] == "Hi, I'm Sam. How can I help?"

    hb = await client.post(f"/v1/inbox/conversations/{cid}/handback", headers=headers)
    assert hb.json()["status"] == "active"

    # Bot resumes after handback.
    resumed = await _public_chat(client, key, "thanks", cid)
    assert resumed["content"] == "echo: thanks"


async def test_notes_tags_assign_close(client: AsyncClient) -> None:
    headers = await _headers(client, "ops2@example.com")
    _aid, key = await _handoff_agent(client, headers)
    cid = (await _public_chat(client, key, "talk to a person"))["conversation_id"]
    me = await client.get("/v1/auth/me", headers={"Authorization": headers["Authorization"]})
    uid = me.json()["user"]["id"]

    note = await client.post(f"/v1/inbox/conversations/{cid}/notes", json={"text": "VIP customer"}, headers=headers)
    assert note.json()["notes"][0]["text"] == "VIP customer"
    tags = await client.post(
        f"/v1/inbox/conversations/{cid}/tags", json={"tags": ["billing", "urgent"]}, headers=headers
    )
    assert tags.json()["tags"] == ["billing", "urgent"]
    asg = await client.post(f"/v1/inbox/conversations/{cid}/assign", json={"user_id": uid}, headers=headers)
    assert asg.json()["handoff"]["assigned_to"] == uid
    closed = await client.post(f"/v1/inbox/conversations/{cid}/close", headers=headers)
    assert closed.json()["status"] == "closed"


# ── Tool-driven handoff (agent calls request_handoff) ────────────────────────────────
async def test_request_handoff_tool(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.modules.conversations import service as chat_service

    async def _provider(*_a: object, **_k: object) -> ScriptedToolProvider:
        return ScriptedToolProvider(
            ToolCall(id="c1", name="request_handoff", arguments={"reason": "cannot resolve"}),
            answer="I've asked a teammate to help.",
        )

    monkeypatch.setattr(chat_service, "_resolve_provider", lambda *a, **k: _provider())

    headers = await _headers(client, "tool@example.com")
    agent = await client.post("/v1/agents", json={"name": "Escalator"}, headers=headers)
    aid = agent.json()["id"]
    await client.patch(
        f"/v1/agents/{aid}/versions/1",
        json={"features": {"tools_enabled": True, "memory_enabled": True, "handoff_enabled": True}},
        headers=headers,
    )
    await client.post(
        "/v1/tools", json={"name": "request_handoff", "type": "builtin", "agent_id": aid}, headers=headers
    )

    r = await client.post(
        f"/v1/agents/{aid}/chat", json={"message": "help me", "stream": False}, headers=headers
    )
    cid = r.json()["conversation_id"]

    inbox = await client.get("/v1/inbox/conversations", headers=headers)
    item = next(i for i in inbox.json() if i["id"] == cid)
    assert item["status"] == "handoff"
    assert item["handoff"]["requested_by"] == "bot"


# ── Inbox WS auth guard ──────────────────────────────────────────────────────────────
def test_inbox_ws_rejects_without_token() -> None:
    app = create_app()
    tc = TestClient(app)
    with pytest.raises(WebSocketDisconnect):
        with tc.websocket_connect("/v1/inbox/ws") as ws:
            ws.receive_text()


# ── Realtime hub fan-out ─────────────────────────────────────────────────────────────
async def test_hub_publishes_to_subscribers() -> None:
    from app.realtime.hub import hub, inbox_topic

    org = uuid.uuid4()
    q = hub.subscribe(inbox_topic(org))
    await hub.publish(inbox_topic(org), {"type": "handoff.requested", "conversation_id": "x"})
    event = await q.get()
    assert event["type"] == "handoff.requested"
    hub.unsubscribe(inbox_topic(org), q)
