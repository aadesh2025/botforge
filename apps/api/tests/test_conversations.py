"""Phase 8 tests: chat persistence, conversation CRUD, memory, and the WS auth guard.

The default agent has no provider key configured, so the runtime falls back to the deterministic
FakeChatProvider (echoes the last user message) — no network needed.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.chat import memory
from app.core.config import settings
from app.llm.fake import FakeChatProvider
from app.main import create_app
from app.modules.conversations import service


@pytest.fixture(autouse=True)
def _fake_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force the deterministic fake provider for both chat and the summarizer.

    The dev .env carries a (now-invalid) GROQ key, so without this the runtime would call the
    real provider and 401. Mirrors the playground test's approach.
    """

    async def _fake(*_a: object, **_k: object) -> FakeChatProvider:
        return FakeChatProvider()

    monkeypatch.setattr(service, "get_chat_provider", _fake)
    monkeypatch.setattr(memory, "get_chat_provider", _fake)


async def _headers(client: AsyncClient, email: str = "chat@example.com") -> dict[str, str]:
    signup = await client.post("/v1/auth/signup", json={"email": email, "password": "password123"})
    token = signup.json()["access_token"]
    org = await client.post("/v1/orgs", json={"name": "ChatOrg"}, headers={"Authorization": f"Bearer {token}"})
    return {"Authorization": f"Bearer {token}", "X-Org-Id": org.json()["id"]}


async def _agent(client: AsyncClient, headers: dict[str, str]) -> str:
    r = await client.post("/v1/agents", json={"name": "Chatbot"}, headers=headers)
    return r.json()["id"]


# ── Streaming chat + persistence ─────────────────────────────────────────────────
async def test_chat_stream_persists_conversation(client: AsyncClient) -> None:
    headers = await _headers(client)
    aid = await _agent(client, headers)

    resp = await client.post(
        f"/v1/agents/{aid}/chat", json={"message": "hello there", "stream": True}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.text
    assert '"type":"conversation"' in body
    assert '"type":"token"' in body
    assert '"type":"message"' in body

    convs = await client.get(f"/v1/conversations?agent_id={aid}", headers=headers)
    assert len(convs.json()) == 1
    conv = convs.json()[0]
    assert conv["message_count"] == 2
    assert conv["title"] == "hello there"

    detail = await client.get(f"/v1/conversations/{conv['id']}", headers=headers)
    msgs = detail.json()["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[1]["content"] == "echo: hello there"


async def test_chat_non_stream(client: AsyncClient) -> None:
    headers = await _headers(client)
    aid = await _agent(client, headers)
    resp = await client.post(
        f"/v1/agents/{aid}/chat", json={"message": "hi", "stream": False}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["content"] == "echo: hi"
    assert data["conversation_id"]
    assert data["message_id"]


async def test_chat_continues_same_conversation(client: AsyncClient) -> None:
    headers = await _headers(client)
    aid = await _agent(client, headers)
    r1 = await client.post(f"/v1/agents/{aid}/chat", json={"message": "one", "stream": False}, headers=headers)
    cid = r1.json()["conversation_id"]

    second = await client.post(
        f"/v1/agents/{aid}/chat", json={"message": "two", "conversation_id": cid, "stream": False}, headers=headers
    )
    assert second.json()["conversation_id"] == cid

    detail = await client.get(f"/v1/conversations/{cid}", headers=headers)
    assert detail.json()["message_count"] == 4  # two user + two assistant


async def test_conversation_crud(client: AsyncClient) -> None:
    headers = await _headers(client)
    aid = await _agent(client, headers)
    r = await client.post(f"/v1/agents/{aid}/chat", json={"message": "hey", "stream": False}, headers=headers)
    cid = r.json()["conversation_id"]

    patched = await client.patch(
        f"/v1/conversations/{cid}", json={"title": "Renamed", "status": "closed"}, headers=headers
    )
    assert patched.json()["title"] == "Renamed"
    assert patched.json()["status"] == "closed"

    msgs = await client.get(f"/v1/conversations/{cid}/messages", headers=headers)
    assert len(msgs.json()) == 2

    assert (await client.delete(f"/v1/conversations/{cid}", headers=headers)).status_code == 204
    assert (await client.get(f"/v1/conversations/{cid}", headers=headers)).status_code == 404


async def test_cross_org_conversation_isolation(client: AsyncClient) -> None:
    a = await _headers(client, "iso_a@example.com")
    aid = await _agent(client, a)
    cid = (await client.post(f"/v1/agents/{aid}/chat", json={"message": "x", "stream": False}, headers=a)).json()[
        "conversation_id"
    ]
    b = await _headers(client, "iso_b@example.com")
    assert (await client.get(f"/v1/conversations/{cid}", headers=b)).status_code == 404


# ── Memory ───────────────────────────────────────────────────────────────────────
async def test_memory_summarizes_over_threshold(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "memory_summary_threshold", 2)
    monkeypatch.setattr(settings, "memory_window_messages", 2)

    headers = await _headers(client)
    aid = await _agent(client, headers)
    cid = None
    for i in range(4):
        body = {"message": f"fact number {i}", "stream": False}
        if cid:
            body["conversation_id"] = cid
        cid = (await client.post(f"/v1/agents/{aid}/chat", json=body, headers=headers)).json()["conversation_id"]

    detail = await client.get(f"/v1/conversations/{cid}", headers=headers)
    assert detail.json()["memory_summary"]  # summarizer folded aged-out turns


# ── WebSocket auth guard ─────────────────────────────────────────────────────────
def test_ws_rejects_without_token() -> None:
    app = create_app()
    tc = TestClient(app)
    with pytest.raises(WebSocketDisconnect):
        with tc.websocket_connect(f"/v1/agents/{uuid.uuid4()}/chat/ws") as ws:
            ws.receive_text()
