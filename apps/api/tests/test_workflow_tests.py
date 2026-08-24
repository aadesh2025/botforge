"""docs/17 Phase 4 follow-up (Workflow Testing, ADR-081): workflow_tests CRUD, the cached-mode
regression runner, and the WORKFLOWS_PUBLISH gate — over the real HTTP client (real DB,
tx-rollback). Mirrors `tests/test_agent_tests.py`'s structure for the equivalent AGENTS_PUBLISH
gate.
"""

from __future__ import annotations

import re
import uuid

import pytest
from httpx import AsyncClient

from app.core.config import settings
from app.core.email import get_email_backend


@pytest.fixture(autouse=True)
def _eager_workflow_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "celery_task_always_eager", True)


TOOL_GRAPH = {
    "nodes": [
        {"id": "s1", "type": "start"},
        {
            "id": "t1", "type": "tool",
            "config": {"tool_name": "lookup", "arguments": {}, "result_variable": "lookup_result"},
        },
        {"id": "e1", "type": "end"},
    ],
    "edges": [
        {"source": "s1", "target": "t1"},
        {"source": "t1", "target": "e1"},
    ],
}

NO_EXTERNAL_GRAPH = {
    "nodes": [
        {"id": "s1", "type": "start"},
        {"id": "sv1", "type": "set_variable", "config": {"key": "greeting", "value": "hello"}},
        {"id": "e1", "type": "end"},
    ],
    "edges": [
        {"source": "s1", "target": "sv1"},
        {"source": "sv1", "target": "e1"},
    ],
}


async def _headers(client: AsyncClient, email: str = "a@example.com") -> tuple[dict[str, str], dict]:
    signup = await client.post("/v1/auth/signup", json={"email": email, "password": "password123"})
    token = signup.json()["access_token"]
    org = await client.post("/v1/orgs", json={"name": "Acme"}, headers={"Authorization": f"Bearer {token}"})
    org_json = org.json()
    return {"Authorization": f"Bearer {token}", "X-Org-Id": org_json["id"]}, org_json


async def _invite_and_join(
    client: AsyncClient, owner_headers: dict[str, str], org: dict, email: str, role: str
) -> dict[str, str]:
    invite = await client.post(
        f"/v1/orgs/{org['id']}/invitations", json={"email": email, "role": role}, headers=owner_headers
    )
    assert invite.status_code == 201, invite.text
    token = re.search(r"Token:\s*(\S+)", get_email_backend().outbox[-1].body).group(1)  # type: ignore[union-attr]
    signup = await client.post("/v1/auth/signup", json={"email": email, "password": "password123"})
    member_token = signup.json()["access_token"]
    await client.post(f"/v1/orgs/invitations/{token}/accept", headers={"Authorization": f"Bearer {member_token}"})
    return {"Authorization": f"Bearer {member_token}", "X-Org-Id": org["id"]}


async def _create_workflow_with_graph(
    client: AsyncClient, headers: dict[str, str], graph: dict, name: str = "Flow"
) -> dict:
    agent = await client.post("/v1/agents", json={"name": "Bot", "description": "d"}, headers=headers)
    assert agent.status_code == 201, agent.text
    workflow = await client.post(
        f"/v1/agents/{agent.json()['id']}/workflows", json={"name": name, "description": "d"}, headers=headers
    )
    assert workflow.status_code == 201, workflow.text
    version = await client.post(
        f"/v1/workflows/{workflow.json()['id']}/versions", json={"graph": graph}, headers=headers
    )
    assert version.status_code == 201, version.text
    return workflow.json()


async def _create_test_case(
    client: AsyncClient, headers: dict[str, str], workflow_id: str, **overrides: object
) -> dict:
    body: dict[str, object] = {
        "name": "Lookup succeeds",
        "input_variables": {},
        "scripted_node_outputs": {"tools": {"lookup": {"output": {"value": 42}, "status": "completed"}}},
        "expected_status": "completed",
        "expected_variables_contains": {},
        "expected_visited_node_ids": ["t1", "e1"],
    }
    body.update(overrides)
    r = await client.post(f"/v1/workflows/{workflow_id}/tests", json=body, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


# ── CRUD ──────────────────────────────────────────────────────────────────────
async def test_create_list_update_delete_workflow_test(client: AsyncClient) -> None:
    headers, _ = await _headers(client)
    workflow = await _create_workflow_with_graph(client, headers, TOOL_GRAPH)
    test = await _create_test_case(client, headers, workflow["id"])
    assert test["enabled"] is True
    assert test["scripted_node_outputs"]["tools"]["lookup"]["output"] == {"value": 42}

    listed = await client.get(f"/v1/workflows/{workflow['id']}/tests", headers=headers)
    assert listed.status_code == 200
    assert [t["id"] for t in listed.json()] == [test["id"]]

    updated = await client.patch(
        f"/v1/workflows/{workflow['id']}/tests/{test['id']}",
        json={"name": "Renamed", "enabled": False}, headers=headers,
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Renamed"
    assert updated.json()["enabled"] is False

    deleted = await client.delete(f"/v1/workflows/{workflow['id']}/tests/{test['id']}", headers=headers)
    assert deleted.status_code == 204
    assert (await client.get(f"/v1/workflows/{workflow['id']}/tests", headers=headers)).json() == []


async def test_workflow_test_from_other_org_is_not_found(client: AsyncClient) -> None:
    headers_a, _ = await _headers(client, "orga@example.com")
    workflow = await _create_workflow_with_graph(client, headers_a, TOOL_GRAPH)
    test = await _create_test_case(client, headers_a, workflow["id"])

    headers_b, _ = await _headers(client, "orgb@example.com")
    r = await client.patch(
        f"/v1/workflows/{workflow['id']}/tests/{test['id']}", json={"name": "hijack"}, headers=headers_b
    )
    assert r.status_code == 404


async def test_viewer_can_read_but_not_write(client: AsyncClient) -> None:
    owner_headers, org = await _headers(client, "owner@example.com")
    workflow = await _create_workflow_with_graph(client, owner_headers, TOOL_GRAPH)
    await _create_test_case(client, owner_headers, workflow["id"])
    viewer_headers = await _invite_and_join(client, owner_headers, org, "viewer@example.com", "viewer")

    listed = await client.get(f"/v1/workflows/{workflow['id']}/tests", headers=viewer_headers)
    assert listed.status_code == 200

    denied = await client.post(
        f"/v1/workflows/{workflow['id']}/tests", json={"name": "x"}, headers=viewer_headers
    )
    assert denied.status_code == 403

    denied_run = await client.post(
        f"/v1/workflows/{workflow['id']}/tests/run", json={}, headers=viewer_headers
    )
    assert denied_run.status_code == 403


# ── Execution (cached mode) ─────────────────────────────────────────────────────
async def test_run_defaults_to_cached_mode(client: AsyncClient) -> None:
    headers, _ = await _headers(client)
    workflow = await _create_workflow_with_graph(client, headers, TOOL_GRAPH)
    await _create_test_case(client, headers, workflow["id"])

    run = await client.post(f"/v1/workflows/{workflow['id']}/tests/run", json={}, headers=headers)
    assert run.status_code == 201, run.text
    [body] = run.json()
    assert body["mode"] == "cached"


async def test_cached_run_passes_when_scripted_matches_expectations(client: AsyncClient) -> None:
    headers, _ = await _headers(client)
    workflow = await _create_workflow_with_graph(client, headers, TOOL_GRAPH)
    await _create_test_case(client, headers, workflow["id"])

    run = await client.post(f"/v1/workflows/{workflow['id']}/tests/run", json={}, headers=headers)
    assert run.status_code == 201, run.text
    [body] = run.json()
    assert body["status"] == "passed", body
    assert body["failure_reasons"] == []
    assert body["actual_status"] == "completed"
    assert "lookup_result" in body["actual_variables"]
    assert set(body["actual_visited_node_ids"]) == {"s1", "t1", "e1"}

    fetched = await client.get(f"/v1/workflow-test-runs/{body['id']}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "passed"


async def test_cached_run_fails_when_expected_status_mismatch(client: AsyncClient) -> None:
    headers, _ = await _headers(client)
    workflow = await _create_workflow_with_graph(client, headers, TOOL_GRAPH)
    await _create_test_case(client, headers, workflow["id"], expected_status="paused_approval")

    run = await client.post(f"/v1/workflows/{workflow['id']}/tests/run", json={}, headers=headers)
    [body] = run.json()
    assert body["status"] == "failed"
    assert any("paused_approval" in reason for reason in body["failure_reasons"])


async def test_cached_run_fails_when_expected_node_not_visited(client: AsyncClient) -> None:
    headers, _ = await _headers(client)
    workflow = await _create_workflow_with_graph(client, headers, TOOL_GRAPH)
    await _create_test_case(client, headers, workflow["id"], expected_visited_node_ids=["never_reached"])

    run = await client.post(f"/v1/workflows/{workflow['id']}/tests/run", json={}, headers=headers)
    [body] = run.json()
    assert body["status"] == "failed"
    assert any("never_reached" in reason for reason in body["failure_reasons"])


async def test_cached_run_fails_when_tool_node_has_no_script(client: AsyncClient) -> None:
    """No scripted output for the tool the graph actually calls — the tool node fails, and
    that failure propagates through to the workflow run's own `failed` status."""
    headers, _ = await _headers(client)
    workflow = await _create_workflow_with_graph(client, headers, TOOL_GRAPH)
    await _create_test_case(
        client, headers, workflow["id"], scripted_node_outputs={"tools": {}}, expected_status="completed",
    )

    run = await client.post(f"/v1/workflows/{workflow['id']}/tests/run", json={}, headers=headers)
    [body] = run.json()
    assert body["status"] == "failed"
    assert body["actual_status"] == "failed"


async def test_run_with_no_enabled_tests_returns_400(client: AsyncClient) -> None:
    headers, _ = await _headers(client)
    workflow = await _create_workflow_with_graph(client, headers, TOOL_GRAPH)
    run = await client.post(f"/v1/workflows/{workflow['id']}/tests/run", json={}, headers=headers)
    assert run.status_code == 400
    assert run.json()["error"]["code"] == "workflow_tests.none_to_run"


async def test_disabled_test_is_skipped_by_run_all(client: AsyncClient) -> None:
    headers, _ = await _headers(client)
    workflow = await _create_workflow_with_graph(client, headers, TOOL_GRAPH)
    await _create_test_case(client, headers, workflow["id"], enabled=False)

    run = await client.post(f"/v1/workflows/{workflow['id']}/tests/run", json={}, headers=headers)
    assert run.status_code == 400  # nothing enabled to run


async def test_run_a_specific_test_id(client: AsyncClient) -> None:
    headers, _ = await _headers(client)
    workflow = await _create_workflow_with_graph(client, headers, TOOL_GRAPH)
    t1 = await _create_test_case(client, headers, workflow["id"], name="one")
    await _create_test_case(client, headers, workflow["id"], name="two")

    run = await client.post(
        f"/v1/workflows/{workflow['id']}/tests/run", json={"test_ids": [t1["id"]]}, headers=headers
    )
    assert run.status_code == 201
    results = run.json()
    assert len(results) == 1
    assert results[0]["workflow_test_id"] == t1["id"]


async def test_list_test_runs_for_workflow(client: AsyncClient) -> None:
    headers, _ = await _headers(client)
    workflow = await _create_workflow_with_graph(client, headers, TOOL_GRAPH)
    await _create_test_case(client, headers, workflow["id"])
    await client.post(f"/v1/workflows/{workflow['id']}/tests/run", json={}, headers=headers)
    await client.post(f"/v1/workflows/{workflow['id']}/tests/run", json={}, headers=headers)

    runs = await client.get(f"/v1/workflows/{workflow['id']}/test-runs", headers=headers)
    assert runs.status_code == 200
    assert len(runs.json()) == 2


async def test_run_unknown_test_ids_returns_400(client: AsyncClient) -> None:
    headers, _ = await _headers(client)
    workflow = await _create_workflow_with_graph(client, headers, TOOL_GRAPH)
    await _create_test_case(client, headers, workflow["id"])
    run = await client.post(
        f"/v1/workflows/{workflow['id']}/tests/run", json={"test_ids": [str(uuid.uuid4())]}, headers=headers
    )
    assert run.status_code == 400


async def test_live_mode_runs_a_graph_with_no_external_nodes(client: AsyncClient) -> None:
    """Live mode builds the REAL tool/agent/sub-workflow executors — proven here on a graph with
    none of those node types, so no real network call is needed to exercise the code path."""
    headers, _ = await _headers(client)
    workflow = await _create_workflow_with_graph(client, headers, NO_EXTERNAL_GRAPH)
    await _create_test_case(
        client, headers, workflow["id"], scripted_node_outputs={}, expected_status="completed",
        expected_variables_contains={"greeting": "hello"}, expected_visited_node_ids=["sv1", "e1"],
    )

    run = await client.post(
        f"/v1/workflows/{workflow['id']}/tests/run", json={"mode": "live"}, headers=headers
    )
    assert run.status_code == 201, run.text
    [body] = run.json()
    assert body["mode"] == "live"
    assert body["status"] == "passed", body


# ── Publish gate (docs/17 Phase 3 DoD, closed for workflows -- ADR-081) ─────────
async def test_publish_blocked_when_latest_batch_has_failures(client: AsyncClient) -> None:
    headers, _ = await _headers(client)
    workflow = await _create_workflow_with_graph(client, headers, TOOL_GRAPH)
    await _create_test_case(client, headers, workflow["id"], expected_status="paused_approval")
    run = await client.post(f"/v1/workflows/{workflow['id']}/tests/run", json={}, headers=headers)
    assert run.json()[0]["status"] == "failed"

    publish = await client.post(f"/v1/workflows/{workflow['id']}/versions/1/publish", headers=headers)
    assert publish.status_code == 400
    assert publish.json()["error"]["code"] == "workflows.tests_failing"


async def test_publish_allowed_when_latest_batch_passes(client: AsyncClient) -> None:
    headers, _ = await _headers(client)
    workflow = await _create_workflow_with_graph(client, headers, TOOL_GRAPH)
    await _create_test_case(client, headers, workflow["id"])
    run = await client.post(f"/v1/workflows/{workflow['id']}/tests/run", json={}, headers=headers)
    assert run.json()[0]["status"] == "passed"

    publish = await client.post(f"/v1/workflows/{workflow['id']}/versions/1/publish", headers=headers)
    assert publish.status_code == 200, publish.text


async def test_publish_unaffected_when_workflow_has_no_tests(client: AsyncClient) -> None:
    """The gate is opt-in (matching ADR-079's own rule) — a workflow that never adopted testing
    publishes exactly as it did before this feature existed."""
    headers, _ = await _headers(client)
    workflow = await _create_workflow_with_graph(client, headers, TOOL_GRAPH)
    publish = await client.post(f"/v1/workflows/{workflow['id']}/versions/1/publish", headers=headers)
    assert publish.status_code == 200, publish.text


async def test_publish_becomes_allowed_again_after_a_later_passing_batch(client: AsyncClient) -> None:
    headers, _ = await _headers(client)
    workflow = await _create_workflow_with_graph(client, headers, TOOL_GRAPH)
    failing = await _create_test_case(
        client, headers, workflow["id"], name="fails", expected_status="paused_approval"
    )
    await client.post(
        f"/v1/workflows/{workflow['id']}/tests/run", json={"test_ids": [failing["id"]]}, headers=headers
    )
    blocked = await client.post(f"/v1/workflows/{workflow['id']}/versions/1/publish", headers=headers)
    assert blocked.status_code == 400

    passing = await _create_test_case(client, headers, workflow["id"], name="passes")
    await client.post(
        f"/v1/workflows/{workflow['id']}/tests/run", json={"test_ids": [passing["id"]]}, headers=headers
    )
    allowed = await client.post(f"/v1/workflows/{workflow['id']}/versions/1/publish", headers=headers)
    assert allowed.status_code == 200, allowed.text
