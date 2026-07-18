"""Phase 10 tests: n8n client signing, workflow parsing, the n8n tool, and the callback."""

from __future__ import annotations

import json
import uuid

import httpx
import pytest
from httpx import AsyncClient

from app.integrations.n8n_client import N8nClient, sign, verify_callback
from app.llm.fake import ScriptedToolProvider
from app.llm.types import ToolCall
from app.models import AgentVersion
from app.tools import n8n_tool
from app.tools.base import ToolContext


def _mock(handler: object) -> httpx.MockTransport:
    return httpx.MockTransport(handler)  # type: ignore[arg-type]


# ── Signing / verification ────────────────────────────────────────────────────────
def test_sign_and_verify_roundtrip() -> None:
    body = b'{"hello":"world"}'
    ts, sig = sign(body)
    assert verify_callback(sig, ts, body) is True
    assert verify_callback("deadbeef", ts, body) is False
    assert verify_callback(sig, ts, b'{"tampered":true}') is False


def test_verify_rejects_stale_timestamp() -> None:
    body = b"{}"
    ts, sig = sign(body, timestamp="1000000000")  # far in the past
    assert verify_callback(sig, ts, body) is False


# ── Client ─────────────────────────────────────────────────────────────────────────
async def test_list_workflows_parses_data() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("x-n8n-api-key") == "k"
        return httpx.Response(200, json={"data": [{"id": "1", "name": "WF", "active": True}]})

    client = N8nClient("http://n8n", "k", transport=_mock(handler))
    workflows = await client.list_workflows()
    assert workflows[0]["name"] == "WF"


def test_extract_webhook_url() -> None:
    client = N8nClient("http://n8n:5678", "k")
    wf = {"nodes": [{"type": "n8n-nodes-base.webhook", "parameters": {"path": "botforge-echo"}}]}
    assert client.extract_webhook_url(wf) == "http://n8n:5678/webhook/botforge-echo"
    assert client.extract_webhook_url({"nodes": []}) is None


async def test_trigger_webhook_signs_request() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["sig"] = request.headers.get("x-botforge-signature")
        captured["ts"] = request.headers.get("x-botforge-timestamp")
        captured["body"] = request.content
        return httpx.Response(200, json={"result": "pong"})

    client = N8nClient("http://n8n", "k", transport=_mock(handler))
    status, data = await client.trigger_webhook("http://n8n/webhook/x", {"a": 1})
    assert status == 200 and data["result"] == "pong"
    assert verify_callback(captured["sig"], captured["ts"], captured["body"]) is True


# ── n8n tool execution ──────────────────────────────────────────────────────────────
def _n8n_ctx() -> ToolContext:
    return ToolContext(
        session=None,  # type: ignore[arg-type]
        org_id=uuid.uuid4(),
        agent_id=uuid.uuid4(),
        version=AgentVersion(agent_id=uuid.uuid4(), version=1),
        run_id=uuid.uuid4(),
    )


async def test_n8n_tool_sync(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(_r: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ticket_id": 42})

    monkeypatch.setattr(n8n_tool, "get_client", lambda **_k: N8nClient("http://n8n", "k", transport=_mock(handler)))
    res = await n8n_tool.execute_n8n_tool(
        {"webhook_url": "http://n8n/webhook/x", "mode": "sync"}, {"q": "hi"}, _n8n_ctx()
    )
    assert res.status == "success"
    assert res.output["response"]["ticket_id"] == 42


async def test_n8n_tool_async_returns_pending(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(_r: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    monkeypatch.setattr(n8n_tool, "get_client", lambda **_k: N8nClient("http://n8n", "k", transport=_mock(handler)))
    res = await n8n_tool.execute_n8n_tool(
        {"webhook_url": "http://n8n/webhook/x", "mode": "async"}, {}, _n8n_ctx()
    )
    assert res.status == "pending"
    assert res.output["status"] == "accepted" and res.output["run_id"]


# ── API: bind + agent uses tool + callback ──────────────────────────────────────────
async def _headers(client: AsyncClient, email: str = "n8n@example.com") -> dict[str, str]:
    signup = await client.post("/v1/auth/signup", json={"email": email, "password": "password123"})
    token = signup.json()["access_token"]
    org = await client.post("/v1/orgs", json={"name": "N8nOrg"}, headers={"Authorization": f"Bearer {token}"})
    return {"Authorization": f"Bearer {token}", "X-Org-Id": org.json()["id"]}


async def test_bind_and_agent_calls_n8n_tool(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.modules.conversations import service as chat_service

    def handler(_r: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"weather": "sunny", "temp_c": 21})

    monkeypatch.setattr(n8n_tool, "get_client", lambda **_k: N8nClient("http://n8n", "k", transport=_mock(handler)))

    async def _provider(*_a: object, **_k: object) -> ScriptedToolProvider:
        return ScriptedToolProvider(
            ToolCall(id="c1", name="get_weather", arguments={"city": "SF"}), answer="it is sunny"
        )

    monkeypatch.setattr(chat_service, "_resolve_provider", lambda *a, **k: _provider())

    headers = await _headers(client)
    agent = await client.post("/v1/agents", json={"name": "WeatherBot"}, headers=headers)
    aid = agent.json()["id"]
    await client.patch(
        f"/v1/agents/{aid}/versions/1",
        json={"features": {"tools_enabled": True, "memory_enabled": True, "handoff_enabled": False}},
        headers=headers,
    )
    bind = await client.post(
        "/v1/tools/n8n/bind",
        json={"name": "get_weather", "webhook_url": "http://n8n/webhook/weather", "mode": "sync", "agent_id": aid},
        headers=headers,
    )
    assert bind.status_code == 201, bind.text
    assert bind.json()["type"] == "n8n"

    resp = await client.post(
        f"/v1/agents/{aid}/chat", json={"message": "weather in SF?", "stream": False}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["content"] == "it is sunny"
    assert data["tool_runs"][0]["output"]["response"]["weather"] == "sunny"

    runs = await client.get("/v1/tools/runs", headers=headers)
    assert runs.json()[0]["status"] == "success"


async def test_n8n_callback_resolves_pending_run(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.modules.conversations import service as chat_service

    def handler(_r: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    monkeypatch.setattr(n8n_tool, "get_client", lambda **_k: N8nClient("http://n8n", "k", transport=_mock(handler)))

    async def _provider(*_a: object, **_k: object) -> ScriptedToolProvider:
        return ScriptedToolProvider(ToolCall(id="c1", name="long_job", arguments={}), answer="working on it")

    monkeypatch.setattr(chat_service, "_resolve_provider", lambda *a, **k: _provider())

    headers = await _headers(client, "n8n2@example.com")
    agent = await client.post("/v1/agents", json={"name": "JobBot"}, headers=headers)
    aid = agent.json()["id"]
    await client.patch(
        f"/v1/agents/{aid}/versions/1",
        json={"features": {"tools_enabled": True, "memory_enabled": True, "handoff_enabled": False}},
        headers=headers,
    )
    await client.post(
        "/v1/tools/n8n/bind",
        json={"name": "long_job", "webhook_url": "http://n8n/webhook/job", "mode": "async", "agent_id": aid},
        headers=headers,
    )
    resp = await client.post(f"/v1/agents/{aid}/chat", json={"message": "start", "stream": False}, headers=headers)
    run_id = resp.json()["tool_runs"][0]["output"]["run_id"]

    # n8n calls back later with a signed payload → resolves the pending run.
    body = json.dumps({"run_id": run_id, "output": {"done": True}, "status": "success"}).encode()
    ts, sig = sign(body)
    cb = await client.post(
        "/v1/tools/n8n/callback",
        content=body,
        headers={"X-BotForge-Signature": sig, "X-BotForge-Timestamp": ts, "Content-Type": "application/json"},
    )
    assert cb.status_code == 200 and cb.json()["ok"] is True

    runs = await client.get("/v1/tools/runs", headers=headers)
    resolved = next(r for r in runs.json() if r["id"] == run_id)
    assert resolved["status"] == "success"
    assert resolved["output"]["done"] is True
