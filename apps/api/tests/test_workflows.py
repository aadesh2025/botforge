"""docs/17 Phase 2: workflow CRUD/versioning/execution over the real HTTP client (real DB,
tx-rollback). Closes the gap ADR-074 flagged as open — the graph engine itself
(`app/workflows/graph.py`) already has thorough unit coverage in `test_workflow_graph.py`; this
file exercises the router/service layer (RBAC, ownership, draft/publish, run/resume/cancel).
"""

from __future__ import annotations

import re

from httpx import AsyncClient

from app.core.email import get_email_backend

LINEAR_GRAPH = {
    "nodes": [
        {"id": "s1", "type": "start"},
        {"id": "m1", "type": "message", "config": {"content": "Hello {{name}}"}},
        {"id": "e1", "type": "end"},
    ],
    "edges": [
        {"source": "s1", "target": "m1"},
        {"source": "m1", "target": "e1"},
    ],
}

APPROVAL_GRAPH = {
    "nodes": [
        {"id": "s1", "type": "start"},
        {"id": "a1", "type": "approval", "config": {"message": "Approve refund?"}},
        {"id": "e_ok", "type": "end"},
        {"id": "e_no", "type": "end"},
    ],
    "edges": [
        {"source": "s1", "target": "a1"},
        {"source": "a1", "target": "e_ok", "condition": "approved"},
        {"source": "a1", "target": "e_no", "condition": "rejected"},
    ],
}

INVALID_GRAPH = {
    "nodes": [{"id": "m1", "type": "message", "config": {"content": "no start or end"}}],
    "edges": [],
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


async def _create_agent(client: AsyncClient, headers: dict[str, str], name: str = "Bot") -> dict:
    r = await client.post("/v1/agents", json={"name": name, "description": "d"}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


async def _create_workflow(
    client: AsyncClient, headers: dict[str, str], agent_id: str, name: str = "Refund flow"
) -> dict:
    r = await client.post(
        f"/v1/agents/{agent_id}/workflows", json={"name": name, "description": "d"}, headers=headers
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _publish_graph(
    client: AsyncClient, headers: dict[str, str], workflow_id: str, graph: dict
) -> dict:
    """Create a version from `graph` and publish it. Returns the published WorkflowOut."""
    version = await client.post(
        f"/v1/workflows/{workflow_id}/versions", json={"graph": graph}, headers=headers
    )
    assert version.status_code == 201, version.text
    published = await client.post(
        f"/v1/workflows/{workflow_id}/versions/{version.json()['version']}/publish", headers=headers
    )
    assert published.status_code == 200, published.text
    return published.json()


# ── CRUD ──────────────────────────────────────────────────────────────────────
async def test_create_list_get_workflow(client: AsyncClient) -> None:
    headers, _ = await _headers(client)
    agent = await _create_agent(client, headers)
    workflow = await _create_workflow(client, headers, agent["id"])
    assert workflow["agent_id"] == agent["id"]
    assert workflow["current_version_id"] is None

    listed = await client.get(f"/v1/agents/{agent['id']}/workflows", headers=headers)
    assert listed.status_code == 200
    assert [w["id"] for w in listed.json()] == [workflow["id"]]

    got = await client.get(f"/v1/workflows/{workflow['id']}", headers=headers)
    assert got.status_code == 200
    assert got.json()["id"] == workflow["id"]


async def test_create_workflow_unknown_agent_returns_404(client: AsyncClient) -> None:
    headers, _ = await _headers(client)
    import uuid

    r = await client.post(
        f"/v1/agents/{uuid.uuid4()}/workflows", json={"name": "Nope"}, headers=headers
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "workflows.agent_not_found"


async def test_update_and_delete_workflow(client: AsyncClient) -> None:
    headers, _ = await _headers(client)
    agent = await _create_agent(client, headers)
    workflow = await _create_workflow(client, headers, agent["id"])

    patched = await client.patch(
        f"/v1/workflows/{workflow['id']}", json={"name": "Renamed"}, headers=headers
    )
    assert patched.status_code == 200
    assert patched.json()["name"] == "Renamed"

    deleted = await client.delete(f"/v1/workflows/{workflow['id']}", headers=headers)
    assert deleted.status_code == 204
    assert (await client.get(f"/v1/workflows/{workflow['id']}", headers=headers)).status_code == 404
    # Soft delete: it no longer shows up in the list either.
    listed = await client.get(f"/v1/agents/{agent['id']}/workflows", headers=headers)
    assert listed.json() == []


# ── Versioning ────────────────────────────────────────────────────────────────
async def test_create_version_rejects_invalid_graph(client: AsyncClient) -> None:
    headers, _ = await _headers(client)
    agent = await _create_agent(client, headers)
    workflow = await _create_workflow(client, headers, agent["id"])

    r = await client.post(
        f"/v1/workflows/{workflow['id']}/versions", json={"graph": INVALID_GRAPH}, headers=headers
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "workflows.invalid_graph"


async def test_version_lifecycle_and_publish(client: AsyncClient) -> None:
    headers, _ = await _headers(client)
    agent = await _create_agent(client, headers)
    workflow = await _create_workflow(client, headers, agent["id"])

    v1 = await client.post(
        f"/v1/workflows/{workflow['id']}/versions", json={"graph": LINEAR_GRAPH}, headers=headers
    )
    assert v1.status_code == 201
    assert v1.json()["version"] == 1
    assert v1.json()["status"] == "draft"

    v2 = await client.post(
        f"/v1/workflows/{workflow['id']}/versions", json={"graph": LINEAR_GRAPH}, headers=headers
    )
    assert v2.json()["version"] == 2  # auto-increments

    versions = await client.get(f"/v1/workflows/{workflow['id']}/versions", headers=headers)
    assert {v["version"] for v in versions.json()} == {1, 2}

    published = await client.post(
        f"/v1/workflows/{workflow['id']}/versions/1/publish", headers=headers
    )
    assert published.status_code == 200
    assert published.json()["current_version_id"] == v1.json()["id"]


# ── Execution ─────────────────────────────────────────────────────────────────
async def test_run_workflow_without_published_version_returns_400(client: AsyncClient) -> None:
    headers, _ = await _headers(client)
    agent = await _create_agent(client, headers)
    workflow = await _create_workflow(client, headers, agent["id"])

    r = await client.post(f"/v1/workflows/{workflow['id']}/run", json={}, headers=headers)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "workflows.not_published"


async def test_run_linear_workflow_completes(client: AsyncClient) -> None:
    headers, _ = await _headers(client)
    agent = await _create_agent(client, headers)
    workflow = await _create_workflow(client, headers, agent["id"])
    await _publish_graph(client, headers, workflow["id"], LINEAR_GRAPH)

    run = await client.post(
        f"/v1/workflows/{workflow['id']}/run", json={"variables": {"name": "Sam"}}, headers=headers
    )
    assert run.status_code == 201, run.text
    body = run.json()
    assert body["status"] == "completed"
    assert body["current_node_id"] is None
    assert body["completed_at"] is not None

    steps = await client.get(f"/v1/workflow-runs/{body['id']}/steps", headers=headers)
    assert steps.status_code == 200
    step_list = steps.json()
    assert [s["node_id"] for s in step_list] == ["s1", "m1", "e1"]
    assert all(s["status"] == "completed" for s in step_list)
    assert step_list[1]["output"]["content"] == "Hello Sam"


async def test_run_workflow_pauses_on_approval_then_resumes(client: AsyncClient) -> None:
    headers, _ = await _headers(client)
    agent = await _create_agent(client, headers)
    workflow = await _create_workflow(client, headers, agent["id"])
    await _publish_graph(client, headers, workflow["id"], APPROVAL_GRAPH)

    run = await client.post(f"/v1/workflows/{workflow['id']}/run", json={}, headers=headers)
    assert run.status_code == 201
    body = run.json()
    assert body["status"] == "paused_approval"
    assert body["current_node_id"] == "a1"

    resumed = await client.post(
        f"/v1/workflow-runs/{body['id']}/resume", json={"decision": "approved"}, headers=headers
    )
    assert resumed.status_code == 200, resumed.text
    resumed_body = resumed.json()
    assert resumed_body["status"] == "completed"
    assert resumed_body["current_node_id"] is None

    steps = (await client.get(f"/v1/workflow-runs/{body['id']}/steps", headers=headers)).json()
    # Approval step recorded once (awaiting_approval), then again on resume (completed).
    assert [s["node_id"] for s in steps] == ["s1", "a1", "a1", "e_ok"]
    assert steps[1]["status"] == "awaiting_approval"
    assert steps[2]["status"] == "completed"


async def test_resume_non_paused_run_returns_400(client: AsyncClient) -> None:
    headers, _ = await _headers(client)
    agent = await _create_agent(client, headers)
    workflow = await _create_workflow(client, headers, agent["id"])
    await _publish_graph(client, headers, workflow["id"], LINEAR_GRAPH)
    run = (await client.post(f"/v1/workflows/{workflow['id']}/run", json={}, headers=headers)).json()

    r = await client.post(
        f"/v1/workflow-runs/{run['id']}/resume", json={"decision": "approved"}, headers=headers
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "workflows.not_paused"


async def test_cancel_workflow_run(client: AsyncClient) -> None:
    headers, _ = await _headers(client)
    agent = await _create_agent(client, headers)
    workflow = await _create_workflow(client, headers, agent["id"])
    await _publish_graph(client, headers, workflow["id"], APPROVAL_GRAPH)
    run = (await client.post(f"/v1/workflows/{workflow['id']}/run", json={}, headers=headers)).json()
    assert run["status"] == "paused_approval"

    cancelled = await client.post(f"/v1/workflow-runs/{run['id']}/cancel", headers=headers)
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    # Cancelling an already-terminal run is a no-op, not an error.
    again = await client.post(f"/v1/workflow-runs/{run['id']}/cancel", headers=headers)
    assert again.status_code == 200
    assert again.json()["status"] == "cancelled"


# ── RBAC ──────────────────────────────────────────────────────────────────────
async def test_viewer_can_read_but_not_write(client: AsyncClient) -> None:
    owner_headers, org = await _headers(client, "owner@example.com")
    agent = await _create_agent(client, owner_headers)
    workflow = await _create_workflow(client, owner_headers, agent["id"])
    viewer_headers = await _invite_and_join(client, owner_headers, org, "viewer@example.com", "viewer")

    listed = await client.get(f"/v1/agents/{agent['id']}/workflows", headers=viewer_headers)
    assert listed.status_code == 200

    denied = await client.post(
        f"/v1/agents/{agent['id']}/workflows", json={"name": "Nope"}, headers=viewer_headers
    )
    assert denied.status_code == 403

    denied_edit = await client.patch(
        f"/v1/workflows/{workflow['id']}", json={"name": "x"}, headers=viewer_headers
    )
    assert denied_edit.status_code == 403


async def test_editor_can_write_and_run_but_not_publish(client: AsyncClient) -> None:
    owner_headers, org = await _headers(client, "owner2@example.com")
    agent = await _create_agent(client, owner_headers)
    editor_headers = await _invite_and_join(client, owner_headers, org, "editor2@example.com", "editor")

    workflow = await _create_workflow(client, editor_headers, agent["id"])
    version = await client.post(
        f"/v1/workflows/{workflow['id']}/versions", json={"graph": LINEAR_GRAPH}, headers=editor_headers
    )
    assert version.status_code == 201

    publish_denied = await client.post(
        f"/v1/workflows/{workflow['id']}/versions/1/publish", headers=editor_headers
    )
    assert publish_denied.status_code == 403

    # Owner publishes on the editor's behalf, then the editor can still run it.
    published = await client.post(
        f"/v1/workflows/{workflow['id']}/versions/1/publish", headers=owner_headers
    )
    assert published.status_code == 200

    run = await client.post(f"/v1/workflows/{workflow['id']}/run", json={}, headers=editor_headers)
    assert run.status_code == 201
    assert run.json()["status"] == "completed"


# ── Cross-org isolation ─────────────────────────────────────────────────────────
async def test_workflow_from_other_org_is_not_found(client: AsyncClient) -> None:
    headers_a, _ = await _headers(client, "orga@example.com")
    agent_a = await _create_agent(client, headers_a)
    workflow_a = await _create_workflow(client, headers_a, agent_a["id"])

    headers_b, _ = await _headers(client, "orgb@example.com")
    r = await client.get(f"/v1/workflows/{workflow_a['id']}", headers=headers_b)
    assert r.status_code == 404

    denied_patch = await client.patch(
        f"/v1/workflows/{workflow_a['id']}", json={"name": "hijack"}, headers=headers_b
    )
    assert denied_patch.status_code == 404


async def test_workflow_run_from_other_org_is_not_found(client: AsyncClient) -> None:
    headers_a, _ = await _headers(client, "orga2@example.com")
    agent_a = await _create_agent(client, headers_a)
    workflow_a = await _create_workflow(client, headers_a, agent_a["id"])
    await _publish_graph(client, headers_a, workflow_a["id"], LINEAR_GRAPH)
    run = (await client.post(f"/v1/workflows/{workflow_a['id']}/run", json={}, headers=headers_a)).json()

    headers_b, _ = await _headers(client, "orgb2@example.com")
    r = await client.get(f"/v1/workflow-runs/{run['id']}/steps", headers=headers_b)
    assert r.status_code == 404
    resume = await client.post(
        f"/v1/workflow-runs/{run['id']}/resume", json={"decision": "approved"}, headers=headers_b
    )
    assert resume.status_code == 404
