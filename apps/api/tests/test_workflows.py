"""docs/17 Phase 2: workflow CRUD/versioning/execution over the real HTTP client (real DB,
tx-rollback). Closes the gap ADR-074 flagged as open — the graph engine itself
(`app/workflows/graph.py`) already has thorough unit coverage in `test_workflow_graph.py`; this
file exercises the router/service layer (RBAC, ownership, draft/publish, run/resume/cancel).

Execution now dispatches through Celery in production (docs/17 Phase 2 item 2). Every test in
this file except the dedicated `TestAsyncDispatch` class runs with `celery_task_always_eager`
forced on, matching `test_email.py`'s convention — eager mode makes `run`/`resume` execute
in-process, synchronously, on the SAME request-scoped session the test's assertions read from,
which is what nearly every test here (written under the old synchronous-only contract) still
assumes. `TestAsyncDispatch` turns it back off to prove the real dispatch path: a `run` returns
`"running"` immediately and a Celery task is enqueued, never executed inline.
"""

from __future__ import annotations

import re

import pytest
from httpx import AsyncClient

from app.core.config import settings
from app.core.email import get_email_backend


@pytest.fixture(autouse=True)
def _eager_workflow_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "celery_task_always_eager", True)

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


# ── Draft-version test-mode execution (docs/17 Phase 2 item 3) ────────────────
async def test_test_run_executes_the_latest_unpublished_draft(client: AsyncClient) -> None:
    headers, _ = await _headers(client)
    agent = await _create_agent(client, headers)
    workflow = await _create_workflow(client, headers, agent["id"])

    version = await client.post(
        f"/v1/workflows/{workflow['id']}/versions", json={"graph": LINEAR_GRAPH}, headers=headers
    )
    assert version.status_code == 201
    assert version.json()["status"] == "draft"  # never published

    run = await client.post(
        f"/v1/workflows/{workflow['id']}/test-run", json={"variables": {"name": "Sam"}}, headers=headers
    )
    assert run.status_code == 201, run.text
    body = run.json()
    assert body["status"] == "completed"
    assert body["is_test"] is True

    # The real /run endpoint still refuses — the workflow genuinely has no published version.
    real_run = await client.post(f"/v1/workflows/{workflow['id']}/run", json={}, headers=headers)
    assert real_run.status_code == 400
    assert real_run.json()["error"]["code"] == "workflows.not_published"


async def test_test_run_uses_the_newest_version_even_after_publish(client: AsyncClient) -> None:
    headers, _ = await _headers(client)
    agent = await _create_agent(client, headers)
    workflow = await _create_workflow(client, headers, agent["id"])
    await _publish_graph(client, headers, workflow["id"], LINEAR_GRAPH)  # v1, published

    edited_graph = {
        "nodes": [
            {"id": "s1", "type": "start"},
            {"id": "m1", "type": "message", "config": {"content": "v2 says hi to {{name}}"}},
            {"id": "e1", "type": "end"},
        ],
        "edges": [{"source": "s1", "target": "m1"}, {"source": "m1", "target": "e1"}],
    }
    v2 = await client.post(
        f"/v1/workflows/{workflow['id']}/versions", json={"graph": edited_graph}, headers=headers
    )
    assert v2.json()["version"] == 2
    assert v2.json()["status"] == "draft"  # not published

    run = await client.post(
        f"/v1/workflows/{workflow['id']}/test-run", json={"variables": {"name": "Sam"}}, headers=headers
    )
    assert run.status_code == 201
    steps = (await client.get(f"/v1/workflow-runs/{run.json()['id']}/steps", headers=headers)).json()
    message_step = next(s for s in steps if s["node_type"] == "message")
    assert message_step["output"]["content"] == "v2 says hi to Sam"  # ran v2, not published v1


async def test_test_run_without_any_version_returns_400(client: AsyncClient) -> None:
    headers, _ = await _headers(client)
    agent = await _create_agent(client, headers)
    workflow = await _create_workflow(client, headers, agent["id"])

    run = await client.post(f"/v1/workflows/{workflow['id']}/test-run", json={}, headers=headers)
    assert run.status_code == 400
    assert run.json()["error"]["code"] == "workflows.no_version"


async def test_editor_can_test_run_without_publish_permission(client: AsyncClient) -> None:
    owner_headers, org = await _headers(client, "owner3@example.com")
    agent = await _create_agent(client, owner_headers)
    editor_headers = await _invite_and_join(client, owner_headers, org, "editor3@example.com", "editor")

    workflow = await _create_workflow(client, editor_headers, agent["id"])
    await client.post(
        f"/v1/workflows/{workflow['id']}/versions", json={"graph": LINEAR_GRAPH}, headers=editor_headers
    )

    run = await client.post(
        f"/v1/workflows/{workflow['id']}/test-run", json={"variables": {"name": "Ed"}}, headers=editor_headers
    )
    assert run.status_code == 201, run.text
    assert run.json()["is_test"] is True


async def test_real_run_is_not_marked_is_test(client: AsyncClient) -> None:
    headers, _ = await _headers(client)
    agent = await _create_agent(client, headers)
    workflow = await _create_workflow(client, headers, agent["id"])
    await _publish_graph(client, headers, workflow["id"], LINEAR_GRAPH)

    run = await client.post(f"/v1/workflows/{workflow['id']}/run", json={}, headers=headers)
    assert run.json()["is_test"] is False


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


# ── Async dispatch (docs/17 Phase 2 item 2): eager forced OFF, proving the REAL path ─────────
class TestAsyncDispatch:
    """Overrides the module's autouse eager fixture to prove the production dispatch path:
    `run`/`resume` enqueue a Celery task and return `"running"` immediately, never executing
    inline. `.delay()` itself is stubbed (matching `test_email.py`'s convention) so this never
    depends on a real broker or worker being reachable in the test environment."""

    @pytest.fixture(autouse=True)
    def _real_dispatch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "celery_task_always_eager", False)

    async def test_run_enqueues_and_returns_running_without_executing(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.worker import tasks as worker_tasks

        calls: list[tuple[object, ...]] = []
        monkeypatch.setattr(
            worker_tasks.run_workflow_task, "delay",
            lambda *a: calls.append(a), raising=False,
        )

        headers, _ = await _headers(client)
        agent = await _create_agent(client, headers)
        workflow = await _create_workflow(client, headers, agent["id"])
        await _publish_graph(client, headers, workflow["id"], LINEAR_GRAPH)

        run = await client.post(f"/v1/workflows/{workflow['id']}/run", json={}, headers=headers)
        assert run.status_code == 201, run.text
        body = run.json()
        assert body["status"] == "running"
        assert body["completed_at"] is None
        assert calls == [(body["id"],)]  # enqueued with this run's id, nothing more

        # Never executed inline: no steps were recorded, and the terminal node never ran.
        steps = await client.get(f"/v1/workflow-runs/{body['id']}/steps", headers=headers)
        assert steps.json() == []

    async def test_resume_enqueues_and_returns_running_without_executing(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.worker import tasks as worker_tasks

        headers, _ = await _headers(client)
        agent = await _create_agent(client, headers)
        workflow = await _create_workflow(client, headers, agent["id"])
        await _publish_graph(client, headers, workflow["id"], APPROVAL_GRAPH)

        # Get to a real paused run first — eager just for this one call, matching how a run
        # would already be paused by the time an operator resumes it for real.
        monkeypatch.setattr(settings, "celery_task_always_eager", True)
        run = (await client.post(f"/v1/workflows/{workflow['id']}/run", json={}, headers=headers)).json()
        assert run["status"] == "paused_approval"
        monkeypatch.setattr(settings, "celery_task_always_eager", False)

        calls: list[tuple[object, ...]] = []
        monkeypatch.setattr(
            worker_tasks.resume_workflow_run_task, "delay",
            lambda *a: calls.append(a), raising=False,
        )

        resumed = await client.post(
            f"/v1/workflow-runs/{run['id']}/resume", json={"decision": "approved"}, headers=headers
        )
        assert resumed.status_code == 200, resumed.text
        body = resumed.json()
        assert body["status"] == "running"  # not "paused_approval" and not "completed"
        assert calls == [(run["id"], "approved")]

        # Still only the one step from the eager run that paused it — resume did not execute.
        steps = (await client.get(f"/v1/workflow-runs/{run['id']}/steps", headers=headers)).json()
        assert [s["node_id"] for s in steps] == ["s1", "a1"]


def test_resumed_budget_wall_clock_restarts_per_process() -> None:
    """docs/17 Phase 2 item 2: a Celery worker executing a run (or a resume) has no relation
    to the process that originally created the budget — `AgentBudget.started_at` is
    deliberately NOT part of the serialized dict, so `max_runtime_s` measures wall-clock time
    from whenever THIS process picked the run up, never a stale reading carried over from
    wherever it was serialized."""
    from app.chat.budget import default_budget
    from app.workflows.service import _budget_from_dict, _budget_to_dict

    original = default_budget()
    original.consumed_steps = 3
    original.consumed_cost_usd = 0.01
    serialized = _budget_to_dict(original)
    assert "started_at" not in serialized

    reconstructed = _budget_from_dict(serialized)
    assert reconstructed.consumed_steps == 3  # spend carried over...
    assert reconstructed.elapsed_s() < 1.0  # ...but the runtime clock did not


# ── Approval → Handoff/inbox integration (docs/17 Phase 2 item 4) ─────────────
async def test_approval_pause_surfaces_in_the_inbox(client: AsyncClient) -> None:
    headers, _ = await _headers(client)
    agent = await _create_agent(client, headers)
    workflow = await _create_workflow(client, headers, agent["id"])
    await _publish_graph(client, headers, workflow["id"], APPROVAL_GRAPH)

    run = (await client.post(f"/v1/workflows/{workflow['id']}/run", json={}, headers=headers)).json()
    assert run["status"] == "paused_approval"

    approvals = await client.get("/v1/inbox/workflow-approvals", headers=headers)
    assert approvals.status_code == 200
    items = approvals.json()
    assert len(items) == 1
    assert items[0]["workflow_run_id"] == run["id"]
    assert items[0]["workflow_id"] == workflow["id"]
    assert items[0]["message"] == "Approve refund?"  # the approval node's own config.message
    assert items[0]["run_status"] == "paused_approval"


async def test_deciding_via_inbox_resumes_the_run_and_clears_the_queue(client: AsyncClient) -> None:
    headers, _ = await _headers(client)
    agent = await _create_agent(client, headers)
    workflow = await _create_workflow(client, headers, agent["id"])
    await _publish_graph(client, headers, workflow["id"], APPROVAL_GRAPH)
    run = (await client.post(f"/v1/workflows/{workflow['id']}/run", json={}, headers=headers)).json()
    handoff_id = (await client.get("/v1/inbox/workflow-approvals", headers=headers)).json()[0]["handoff_id"]

    decided = await client.post(
        f"/v1/inbox/workflow-approvals/{handoff_id}/decide", json={"decision": "approved"}, headers=headers
    )
    assert decided.status_code == 200, decided.text
    assert decided.json()["run_status"] == "completed"

    # Resolved: no longer in the queue.
    approvals = await client.get("/v1/inbox/workflow-approvals", headers=headers)
    assert approvals.json() == []

    # And the run really did take the "approved" branch.
    steps = (await client.get(f"/v1/workflow-runs/{run['id']}/steps", headers=headers)).json()
    assert [s["node_id"] for s in steps][-1] == "e_ok"


async def test_deciding_rejected_takes_the_rejected_branch(client: AsyncClient) -> None:
    headers, _ = await _headers(client)
    agent = await _create_agent(client, headers)
    workflow = await _create_workflow(client, headers, agent["id"])
    await _publish_graph(client, headers, workflow["id"], APPROVAL_GRAPH)
    run = (await client.post(f"/v1/workflows/{workflow['id']}/run", json={}, headers=headers)).json()
    handoff_id = (await client.get("/v1/inbox/workflow-approvals", headers=headers)).json()[0]["handoff_id"]

    await client.post(
        f"/v1/inbox/workflow-approvals/{handoff_id}/decide", json={"decision": "rejected"}, headers=headers
    )
    steps = (await client.get(f"/v1/workflow-runs/{run['id']}/steps", headers=headers)).json()
    assert [s["node_id"] for s in steps][-1] == "e_no"


async def test_cancelling_a_paused_run_also_clears_the_inbox_queue(client: AsyncClient) -> None:
    headers, _ = await _headers(client)
    agent = await _create_agent(client, headers)
    workflow = await _create_workflow(client, headers, agent["id"])
    await _publish_graph(client, headers, workflow["id"], APPROVAL_GRAPH)
    run = (await client.post(f"/v1/workflows/{workflow['id']}/run", json={}, headers=headers)).json()

    await client.post(f"/v1/workflow-runs/{run['id']}/cancel", headers=headers)
    approvals = await client.get("/v1/inbox/workflow-approvals", headers=headers)
    assert approvals.json() == []


async def test_deciding_unknown_handoff_returns_404(client: AsyncClient) -> None:
    headers, _ = await _headers(client)
    import uuid

    r = await client.post(
        f"/v1/inbox/workflow-approvals/{uuid.uuid4()}/decide", json={"decision": "approved"}, headers=headers
    )
    assert r.status_code == 404


async def test_deciding_already_resolved_handoff_returns_400(client: AsyncClient) -> None:
    headers, _ = await _headers(client)
    agent = await _create_agent(client, headers)
    workflow = await _create_workflow(client, headers, agent["id"])
    await _publish_graph(client, headers, workflow["id"], APPROVAL_GRAPH)
    await client.post(f"/v1/workflows/{workflow['id']}/run", json={}, headers=headers)
    handoff_id = (await client.get("/v1/inbox/workflow-approvals", headers=headers)).json()[0]["handoff_id"]

    first = await client.post(
        f"/v1/inbox/workflow-approvals/{handoff_id}/decide", json={"decision": "approved"}, headers=headers
    )
    assert first.status_code == 200
    second = await client.post(
        f"/v1/inbox/workflow-approvals/{handoff_id}/decide", json={"decision": "approved"}, headers=headers
    )
    assert second.status_code == 400
    assert second.json()["error"]["code"] == "inbox.workflow_approval_already_resolved"


async def test_operator_can_decide_via_inbox_without_workflows_write(client: AsyncClient) -> None:
    """The point of the split: `operator` has INBOX_HANDLE but NOT WORKFLOWS_WRITE, so the raw
    resume endpoint refuses them while the inbox decide endpoint — the intended path for this
    role — accepts them."""
    owner_headers, org = await _headers(client, "owner4@example.com")
    agent = await _create_agent(client, owner_headers)
    workflow = await _create_workflow(client, owner_headers, agent["id"])
    await _publish_graph(client, owner_headers, workflow["id"], APPROVAL_GRAPH)
    run = (await client.post(f"/v1/workflows/{workflow['id']}/run", json={}, headers=owner_headers)).json()
    handoff_id = (
        await client.get("/v1/inbox/workflow-approvals", headers=owner_headers)
    ).json()[0]["handoff_id"]

    operator_headers = await _invite_and_join(client, owner_headers, org, "operator4@example.com", "operator")

    denied = await client.post(
        f"/v1/workflow-runs/{run['id']}/resume", json={"decision": "approved"}, headers=operator_headers
    )
    assert denied.status_code == 403

    decided = await client.post(
        f"/v1/inbox/workflow-approvals/{handoff_id}/decide",
        json={"decision": "approved"}, headers=operator_headers,
    )
    assert decided.status_code == 200, decided.text


async def test_viewer_cannot_list_or_decide_workflow_approvals(client: AsyncClient) -> None:
    owner_headers, org = await _headers(client, "owner5@example.com")
    agent = await _create_agent(client, owner_headers)
    workflow = await _create_workflow(client, owner_headers, agent["id"])
    await _publish_graph(client, owner_headers, workflow["id"], APPROVAL_GRAPH)
    run = (await client.post(f"/v1/workflows/{workflow['id']}/run", json={}, headers=owner_headers)).json()
    handoff_id = (
        await client.get("/v1/inbox/workflow-approvals", headers=owner_headers)
    ).json()[0]["handoff_id"]

    viewer_headers = await _invite_and_join(client, owner_headers, org, "viewer5@example.com", "viewer")

    assert (await client.get("/v1/inbox/workflow-approvals", headers=viewer_headers)).status_code == 403
    denied = await client.post(
        f"/v1/inbox/workflow-approvals/{handoff_id}/decide",
        json={"decision": "approved"}, headers=viewer_headers,
    )
    assert denied.status_code == 403
    assert run["status"] == "paused_approval"  # untouched
