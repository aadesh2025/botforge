"""docs/17 Phase 3 (Agent Testing, ADR-079): agent_tests CRUD, the cached-mode regression
runner, and the publish gate — over the real HTTP client (real DB, tx-rollback).
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient


async def _headers(client: AsyncClient, email: str = "a@example.com") -> tuple[dict[str, str], dict]:
    signup = await client.post("/v1/auth/signup", json={"email": email, "password": "password123"})
    token = signup.json()["access_token"]
    org = await client.post("/v1/orgs", json={"name": "Acme"}, headers={"Authorization": f"Bearer {token}"})
    org_json = org.json()
    return {"Authorization": f"Bearer {token}", "X-Org-Id": org_json["id"]}, org_json


async def _invite_and_join(
    client: AsyncClient, owner_headers: dict[str, str], org: dict, email: str, role: str
) -> dict[str, str]:
    import re

    from app.core.email import get_email_backend

    invite = await client.post(
        f"/v1/orgs/{org['id']}/invitations", json={"email": email, "role": role}, headers=owner_headers
    )
    assert invite.status_code == 201, invite.text
    token = re.search(r"Token:\s*(\S+)", get_email_backend().outbox[-1].body).group(1)  # type: ignore[union-attr]
    signup = await client.post("/v1/auth/signup", json={"email": email, "password": "password123"})
    member_token = signup.json()["access_token"]
    await client.post(f"/v1/orgs/invitations/{token}/accept", headers={"Authorization": f"Bearer {member_token}"})
    return {"Authorization": f"Bearer {member_token}", "X-Org-Id": org["id"]}


async def _create_agent_with_calculator(client: AsyncClient, headers: dict[str, str], name: str = "Bot") -> dict:
    """An agent with tools enabled and a real, network-free builtin tool bound — the calculator
    — so a scripted tool call in a test case has something real to dispatch to."""
    agent_res = await client.post("/v1/agents", json={"name": name, "description": "d"}, headers=headers)
    assert agent_res.status_code == 201, agent_res.text
    agent = agent_res.json()
    patched = await client.patch(
        f"/v1/agents/{agent['id']}/versions/1",
        json={"features": {"tools_enabled": True}},
        headers=headers,
    )
    assert patched.status_code == 200, patched.text
    tool_res = await client.post(
        "/v1/tools",
        json={"name": "calculator", "type": "builtin", "agent_id": agent["id"]},
        headers=headers,
    )
    assert tool_res.status_code == 201, tool_res.text
    return agent


async def _create_test_case(
    client: AsyncClient, headers: dict[str, str], agent_id: str, **overrides: object
) -> dict:
    body = {
        "name": "Basic math",
        "input_message": "What is 2 + 2?",
        "scripted_tool_calls": [{"name": "calculator", "arguments": {"expression": "2 + 2"}}],
        "scripted_final_answer": "The answer is 4.",
        "expected_tool_calls": [{"name": "calculator"}],
        "expected_final_answer_contains": "4",
    }
    body.update(overrides)
    r = await client.post(f"/v1/agents/{agent_id}/tests", json=body, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


# ── CRUD ──────────────────────────────────────────────────────────────────────
async def test_create_list_update_delete_agent_test(client: AsyncClient) -> None:
    headers, _ = await _headers(client)
    agent = await _create_agent_with_calculator(client, headers)
    test = await _create_test_case(client, headers, agent["id"])
    assert test["enabled"] is True
    assert test["scripted_tool_calls"] == [{"name": "calculator", "arguments": {"expression": "2 + 2"}}]

    listed = await client.get(f"/v1/agents/{agent['id']}/tests", headers=headers)
    assert listed.status_code == 200
    assert [t["id"] for t in listed.json()] == [test["id"]]

    updated = await client.patch(
        f"/v1/agents/{agent['id']}/tests/{test['id']}", json={"name": "Renamed", "enabled": False}, headers=headers
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Renamed"
    assert updated.json()["enabled"] is False

    deleted = await client.delete(f"/v1/agents/{agent['id']}/tests/{test['id']}", headers=headers)
    assert deleted.status_code == 204
    assert (await client.get(f"/v1/agents/{agent['id']}/tests", headers=headers)).json() == []


async def test_agent_test_from_other_org_is_not_found(client: AsyncClient) -> None:
    headers_a, _ = await _headers(client, "orga@example.com")
    agent = await _create_agent_with_calculator(client, headers_a)
    test = await _create_test_case(client, headers_a, agent["id"])

    headers_b, _ = await _headers(client, "orgb@example.com")
    r = await client.patch(
        f"/v1/agents/{agent['id']}/tests/{test['id']}", json={"name": "hijack"}, headers=headers_b
    )
    assert r.status_code == 404


async def test_viewer_can_read_but_not_write(client: AsyncClient) -> None:
    owner_headers, org = await _headers(client, "owner@example.com")
    agent = await _create_agent_with_calculator(client, owner_headers)
    await _create_test_case(client, owner_headers, agent["id"])
    viewer_headers = await _invite_and_join(client, owner_headers, org, "viewer@example.com", "viewer")

    listed = await client.get(f"/v1/agents/{agent['id']}/tests", headers=viewer_headers)
    assert listed.status_code == 200

    denied = await client.post(
        f"/v1/agents/{agent['id']}/tests",
        json={"name": "x", "input_message": "hi"},
        headers=viewer_headers,
    )
    assert denied.status_code == 403

    denied_run = await client.post(f"/v1/agents/{agent['id']}/tests/run", json={}, headers=viewer_headers)
    assert denied_run.status_code == 403


# ── Execution (cached mode) ─────────────────────────────────────────────────────
async def test_run_defaults_to_cached_mode(client: AsyncClient) -> None:
    headers, _ = await _headers(client)
    agent = await _create_agent_with_calculator(client, headers)
    await _create_test_case(client, headers, agent["id"])

    run = await client.post(f"/v1/agents/{agent['id']}/tests/run", json={}, headers=headers)
    assert run.status_code == 201, run.text
    [body] = run.json()
    assert body["mode"] == "cached"


async def test_cached_run_passes_when_scripted_matches_expectations(client: AsyncClient) -> None:
    headers, _ = await _headers(client)
    agent = await _create_agent_with_calculator(client, headers)
    await _create_test_case(client, headers, agent["id"])

    run = await client.post(f"/v1/agents/{agent['id']}/tests/run", json={}, headers=headers)
    assert run.status_code == 201, run.text
    [body] = run.json()
    assert body["status"] == "passed", body
    assert body["failure_reasons"] == []
    assert body["actual_tool_calls"] == [{"name": "calculator", "arguments": {"expression": "2 + 2"}}]
    assert "4" in (body["actual_final_answer"] or "")

    fetched = await client.get(f"/v1/agent-test-runs/{body['id']}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "passed"


async def test_cached_run_fails_when_expected_tool_call_not_observed(client: AsyncClient) -> None:
    headers, _ = await _headers(client)
    agent = await _create_agent_with_calculator(client, headers)
    await _create_test_case(
        client, headers, agent["id"], expected_tool_calls=[{"name": "some_other_tool"}]
    )

    run = await client.post(f"/v1/agents/{agent['id']}/tests/run", json={}, headers=headers)
    [body] = run.json()
    assert body["status"] == "failed"
    assert any("some_other_tool" in reason for reason in body["failure_reasons"])


async def test_cached_run_fails_when_final_answer_missing_expected_substring(client: AsyncClient) -> None:
    headers, _ = await _headers(client)
    agent = await _create_agent_with_calculator(client, headers)
    await _create_test_case(client, headers, agent["id"], expected_final_answer_contains="nonexistent phrase")

    run = await client.post(f"/v1/agents/{agent['id']}/tests/run", json={}, headers=headers)
    [body] = run.json()
    assert body["status"] == "failed"
    assert any("nonexistent phrase" in reason for reason in body["failure_reasons"])


async def test_run_with_no_enabled_tests_returns_400(client: AsyncClient) -> None:
    headers, _ = await _headers(client)
    agent = await _create_agent_with_calculator(client, headers)
    run = await client.post(f"/v1/agents/{agent['id']}/tests/run", json={}, headers=headers)
    assert run.status_code == 400
    assert run.json()["error"]["code"] == "agent_tests.none_to_run"


async def test_disabled_test_is_skipped_by_run_all(client: AsyncClient) -> None:
    headers, _ = await _headers(client)
    agent = await _create_agent_with_calculator(client, headers)
    await _create_test_case(client, headers, agent["id"], enabled=False)

    run = await client.post(f"/v1/agents/{agent['id']}/tests/run", json={}, headers=headers)
    assert run.status_code == 400  # nothing enabled to run


async def test_run_a_specific_test_id(client: AsyncClient) -> None:
    headers, _ = await _headers(client)
    agent = await _create_agent_with_calculator(client, headers)
    t1 = await _create_test_case(client, headers, agent["id"], name="one")
    await _create_test_case(client, headers, agent["id"], name="two")

    run = await client.post(
        f"/v1/agents/{agent['id']}/tests/run", json={"test_ids": [t1["id"]]}, headers=headers
    )
    assert run.status_code == 201
    results = run.json()
    assert len(results) == 1
    assert results[0]["agent_test_id"] == t1["id"]


async def test_list_test_runs_for_agent(client: AsyncClient) -> None:
    headers, _ = await _headers(client)
    agent = await _create_agent_with_calculator(client, headers)
    await _create_test_case(client, headers, agent["id"])
    await client.post(f"/v1/agents/{agent['id']}/tests/run", json={}, headers=headers)
    await client.post(f"/v1/agents/{agent['id']}/tests/run", json={}, headers=headers)

    runs = await client.get(f"/v1/agents/{agent['id']}/test-runs", headers=headers)
    assert runs.status_code == 200
    assert len(runs.json()) == 2


# ── Publish gate (docs/17 Phase 3 DoD) ──────────────────────────────────────────
async def test_publish_blocked_when_latest_batch_has_failures(client: AsyncClient) -> None:
    headers, _ = await _headers(client)
    agent = await _create_agent_with_calculator(client, headers)
    await _create_test_case(client, headers, agent["id"], expected_final_answer_contains="never appears")
    run = await client.post(f"/v1/agents/{agent['id']}/tests/run", json={}, headers=headers)
    assert run.json()[0]["status"] == "failed"

    publish = await client.post(f"/v1/agents/{agent['id']}/versions/1/publish", headers=headers)
    assert publish.status_code == 400
    assert publish.json()["error"]["code"] == "agents.tests_failing"


async def test_publish_allowed_when_latest_batch_passes(client: AsyncClient) -> None:
    headers, _ = await _headers(client)
    agent = await _create_agent_with_calculator(client, headers)
    await _create_test_case(client, headers, agent["id"])
    run = await client.post(f"/v1/agents/{agent['id']}/tests/run", json={}, headers=headers)
    assert run.json()[0]["status"] == "passed"

    publish = await client.post(f"/v1/agents/{agent['id']}/versions/1/publish", headers=headers)
    assert publish.status_code == 200, publish.text


async def test_publish_unaffected_when_agent_has_no_tests(client: AsyncClient) -> None:
    """The gate is opt-in (ADR-079) — an agent that never adopted testing publishes exactly as
    it did before Phase 3 existed."""
    headers, _ = await _headers(client)
    agent = await _create_agent_with_calculator(client, headers)
    publish = await client.post(f"/v1/agents/{agent['id']}/versions/1/publish", headers=headers)
    assert publish.status_code == 200, publish.text


async def test_publish_becomes_allowed_again_after_a_later_passing_batch(client: AsyncClient) -> None:
    """"The latest test run" means the latest BATCH, not any historical case in isolation — a
    fresh passing run un-blocks publish even though an earlier batch failed."""
    headers, _ = await _headers(client)
    agent = await _create_agent_with_calculator(client, headers)
    failing = await _create_test_case(
        client, headers, agent["id"], name="fails", expected_final_answer_contains="never appears"
    )
    await client.post(
        f"/v1/agents/{agent['id']}/tests/run", json={"test_ids": [failing["id"]]}, headers=headers
    )
    blocked = await client.post(f"/v1/agents/{agent['id']}/versions/1/publish", headers=headers)
    assert blocked.status_code == 400

    passing = await _create_test_case(client, headers, agent["id"], name="passes")
    # Run only the passing case — that becomes the new latest batch.
    await client.post(
        f"/v1/agents/{agent['id']}/tests/run", json={"test_ids": [passing["id"]]}, headers=headers
    )
    allowed = await client.post(f"/v1/agents/{agent['id']}/versions/1/publish", headers=headers)
    assert allowed.status_code == 200, allowed.text


async def test_run_unknown_test_ids_404_is_not_applicable_and_returns_400(client: AsyncClient) -> None:
    """Requesting only nonexistent test ids matches nothing enabled — same 400 as an empty
    test suite, not a 404 (the agent itself is real)."""
    headers, _ = await _headers(client)
    agent = await _create_agent_with_calculator(client, headers)
    await _create_test_case(client, headers, agent["id"])
    run = await client.post(
        f"/v1/agents/{agent['id']}/tests/run", json={"test_ids": [str(uuid.uuid4())]}, headers=headers
    )
    assert run.status_code == 400
