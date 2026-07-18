"""Phase 9 tests: built-in tools, the tool-calling loop, tool CRUD/test, and tool_runs."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.chat.runtime import TurnResult, run_turn
from app.llm.fake import ScriptedToolProvider
from app.llm.types import ChatRequest, Message, ToolCall, ToolSpec
from app.models import AgentVersion
from app.tools.base import ToolContext
from app.tools.builtins import BUILTINS
from app.tools.http_tool import execute_http_tool


def _ctx() -> ToolContext:
    return ToolContext(
        session=None,  # type: ignore[arg-type]
        org_id=uuid.uuid4(),
        agent_id=uuid.uuid4(),
        version=AgentVersion(agent_id=uuid.uuid4(), version=1, rag_config={}),
    )


# ── Built-in tool implementations ────────────────────────────────────────────────
async def test_calculator() -> None:
    res = await BUILTINS["calculator"].run(_ctx(), {"expression": "(3 + 4) * 2"})
    assert res.status == "success"
    assert res.output["result"] == 14.0


async def test_calculator_rejects_bad_expr() -> None:
    res = await BUILTINS["calculator"].run(_ctx(), {"expression": "__import__('os')"})
    assert res.status == "error"


async def test_get_datetime() -> None:
    res = await BUILTINS["get_datetime"].run(_ctx(), {})
    assert res.status == "success" and "utc" in res.output


async def test_http_request_blocks_private_host() -> None:
    res = await BUILTINS["http_request"].run(_ctx(), {"url": "http://localhost:8000/readyz"})
    assert res.status == "error"
    assert "private" in (res.error or "").lower()


async def test_web_search_stub() -> None:
    res = await BUILTINS["web_search"].run(_ctx(), {"query": "anything"})
    assert res.output["results"] == []


async def test_http_tool_blocks_ssrf() -> None:
    res = await execute_http_tool({"url": "http://127.0.0.1/secret", "method": "GET"}, {})
    assert res.status == "error"


# ── Tool-calling loop (runtime) ──────────────────────────────────────────────────
async def test_run_turn_executes_tool_then_answers() -> None:
    call = ToolCall(id="c1", name="calc", arguments={"x": 1})
    provider = ScriptedToolProvider(call, answer="the answer is done")

    async def executor(_c: ToolCall) -> dict:
        return {"output": {"result": 42}, "status": "success", "error": None}

    req = ChatRequest(
        model="m", messages=[Message(role="user", content="go")], tools=[ToolSpec(name="calc")]
    )
    result = TurnResult()
    events = [e async for e in run_turn(provider, req, [], result, executor=executor, max_iters=4)]
    types = [e.type for e in events]
    assert "tool_call" in types
    assert "tool_result" in types
    assert types[-1] == "done"
    assert result.content.strip() == "the answer is done"
    assert result.tool_runs and result.tool_runs[0]["name"] == "calc"


# ── CRUD + test endpoint ─────────────────────────────────────────────────────────
async def _headers(client: AsyncClient, email: str = "tools@example.com") -> dict[str, str]:
    signup = await client.post("/v1/auth/signup", json={"email": email, "password": "password123"})
    token = signup.json()["access_token"]
    org = await client.post("/v1/orgs", json={"name": "ToolsOrg"}, headers={"Authorization": f"Bearer {token}"})
    return {"Authorization": f"Bearer {token}", "X-Org-Id": org.json()["id"]}


async def test_builtin_catalog_and_crud(client: AsyncClient) -> None:
    headers = await _headers(client)
    builtins = await client.get("/v1/tools/builtin", headers=headers)
    names = {b["name"] for b in builtins.json()}
    assert {"calculator", "get_datetime", "knowledge_search", "http_request", "web_search"} <= names

    created = await client.post("/v1/tools", json={"name": "calculator", "type": "builtin"}, headers=headers)
    assert created.status_code == 201, created.text
    assert created.json()["input_schema"]["properties"]["expression"]  # schema mirrored

    tid = created.json()["id"]
    tested = await client.post(f"/v1/tools/{tid}/test", json={"input": {"expression": "6*7"}}, headers=headers)
    assert tested.json()["status"] == "success"
    assert tested.json()["output"]["result"] == 42.0

    runs = await client.get("/v1/tools/runs", headers=headers)
    assert any(r["tool_id"] == tid for r in runs.json())


async def test_http_tool_requires_url(client: AsyncClient) -> None:
    headers = await _headers(client, "tools2@example.com")
    r = await client.post("/v1/tools", json={"name": "myapi", "type": "http", "config": {}}, headers=headers)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "tools.url_required"


# ── Agent calls a tool mid-conversation ──────────────────────────────────────────
async def test_agent_calls_tool_in_chat(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.modules.conversations import service

    call = ToolCall(id="c1", name="calculator", arguments={"expression": "2+2"})
    monkeypatch.setattr(service, "get_chat_provider", None)  # ensure not used directly

    async def _provider(*_a: object, **_k: object) -> ScriptedToolProvider:
        return ScriptedToolProvider(call, answer="the sum is four")

    monkeypatch.setattr(service, "_resolve_provider", lambda *a, **k: _provider())

    headers = await _headers(client, "tooluse@example.com")
    agent = await client.post("/v1/agents", json={"name": "Tooler"}, headers=headers)
    aid = agent.json()["id"]
    # Enable tools on the agent and attach the calculator built-in.
    await client.patch(
        f"/v1/agents/{aid}/versions/1",
        json={"features": {"tools_enabled": True, "memory_enabled": True, "handoff_enabled": False}},
        headers=headers,
    )
    await client.post(
        "/v1/tools", json={"name": "calculator", "type": "builtin", "agent_id": aid}, headers=headers
    )

    resp = await client.post(
        f"/v1/agents/{aid}/chat", json={"message": "what is 2+2?", "stream": False}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["content"] == "the sum is four"
    assert data["tool_runs"] and data["tool_runs"][0]["name"] == "calculator"

    runs = await client.get(f"/v1/tools/runs?conversation_id={data['conversation_id']}", headers=headers)
    assert len(runs.json()) == 1
    assert runs.json()[0]["status"] == "success"
    assert runs.json()[0]["output"]["result"] == 4.0
