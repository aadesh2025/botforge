"""Phase 17 tests: platform-staff admin console endpoints.

Staff endpoints are org-agnostic and gated by `require_staff` (user.is_staff).
Non-staff (and unauthenticated) requests must be rejected with 403.
"""

from __future__ import annotations

import uuid

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.n8n_client import N8nClient
from app.models import Tool, User
from app.modules.admin import service as admin_service


def _mock(handler) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


async def _signup(client: AsyncClient, email: str) -> str:
    r = await client.post("/v1/auth/signup", json={"email": email, "password": "password123"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


async def _make_staff(db_session: AsyncSession, email: str) -> None:
    user = (await db_session.execute(select(User).where(User.email == email))).scalar_one()
    user.is_staff = True
    await db_session.flush()


async def test_non_staff_blocked_from_all_admin_endpoints(client: AsyncClient) -> None:
    token = await _signup(client, "plain@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    for path in ("/v1/admin/orgs", "/v1/admin/users", "/v1/admin/usage", "/v1/admin/health", "/v1/admin/feature-flags"):
        r = await client.get(path, headers=headers)
        assert r.status_code == 403, f"{path} -> {r.status_code} {r.text}"


async def test_unauthenticated_blocked(client: AsyncClient) -> None:
    r = await client.get("/v1/admin/orgs")
    assert r.status_code in (401, 403), r.text


async def test_staff_can_list_orgs_and_users(client: AsyncClient, db_session: AsyncSession) -> None:
    token = await _signup(client, "staff@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    # Create an org so there is something to aggregate.
    await client.post("/v1/orgs", json={"name": "StaffOrg"}, headers=headers)
    await _make_staff(db_session, "staff@example.com")

    orgs = await client.get("/v1/admin/orgs", headers=headers)
    assert orgs.status_code == 200, orgs.text
    names = [o["name"] for o in orgs.json()]
    assert "StaffOrg" in names
    row = next(o for o in orgs.json() if o["name"] == "StaffOrg")
    assert row["members"] >= 1  # the creator

    users = await client.get("/v1/admin/users", headers=headers)
    assert users.status_code == 200, users.text
    emails = [u["email"] for u in users.json()]
    assert "staff@example.com" in emails
    me = next(u for u in users.json() if u["email"] == "staff@example.com")
    assert me["is_staff"] is True


async def test_staff_usage_and_health(client: AsyncClient, db_session: AsyncSession) -> None:
    token = await _signup(client, "staff2@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    await _make_staff(db_session, "staff2@example.com")

    usage = await client.get("/v1/admin/usage", headers=headers)
    assert usage.status_code == 200, usage.text
    body = usage.json()
    assert body["users"] >= 1
    assert "top_orgs" in body

    health = await client.get("/v1/admin/health", headers=headers)
    assert health.status_code == 200, health.text
    assert health.json()["database"] is True


async def test_staff_feature_flag_upsert_roundtrip(client: AsyncClient, db_session: AsyncSession) -> None:
    token = await _signup(client, "staff3@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    await _make_staff(db_session, "staff3@example.com")

    # Create.
    put = await client.put(
        "/v1/admin/feature-flags/new_dashboard",
        json={"enabled": True, "description": "Beta dashboard"},
        headers=headers,
    )
    assert put.status_code == 200, put.text
    assert put.json()["enabled"] is True

    # Update (on-conflict path).
    put2 = await client.put(
        "/v1/admin/feature-flags/new_dashboard",
        json={"enabled": False, "description": "Rolled back"},
        headers=headers,
    )
    assert put2.status_code == 200, put2.text
    assert put2.json()["enabled"] is False

    flags = await client.get("/v1/admin/feature-flags", headers=headers)
    assert flags.status_code == 200, flags.text
    flag = next(f for f in flags.json() if f["key"] == "new_dashboard")
    assert flag["enabled"] is False
    assert flag["description"] == "Rolled back"


async def test_non_staff_cannot_write_feature_flags(client: AsyncClient) -> None:
    token = await _signup(client, "plain2@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    r = await client.put(
        "/v1/admin/feature-flags/x", json={"enabled": True}, headers=headers
    )
    assert r.status_code == 403, r.text


# ── Cross-org automations overview (ADR-040 tagging backlog, staff-only) ────────────
async def test_non_staff_blocked_from_automations(client: AsyncClient) -> None:
    token = await _signup(client, "plain3@example.com")
    r = await client.get("/v1/admin/automations", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403, r.text


async def test_automations_overview_resolves_owner_from_tags(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Staff see every workflow — including the internal and unowned ones a client never
    would — each resolved to the org its tags name."""
    token = await _signup(client, "autostaff@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    org = await client.post("/v1/orgs", json={"name": "Tagged Co"}, headers=headers)
    slug = org.json()["slug"]
    await _make_staff(db_session, "autostaff@example.com")

    def handler(_r: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    {"id": "w1", "name": "Tagged Co — Booking", "active": True,
                     "tags": [{"name": slug}], "nodes": []},
                    {"id": "w2", "name": "Orphan Flow", "active": False, "tags": [], "nodes": []},
                    {"id": "w3", "name": "Provisioner", "active": True,
                     "tags": [{"name": "internal"}], "nodes": []},
                    {"id": "w4", "name": "Starter", "active": True,
                     "tags": [{"name": "shared-template"}], "nodes": []},
                    {"id": "w5", "name": "Typo Flow", "active": True,
                     "tags": [{"name": "no-such-org"}], "nodes": []},
                ]
            },
        )

    monkeypatch.setattr(
        admin_service, "get_n8n_client", lambda **_k: N8nClient("http://n8n", "k", transport=_mock(handler))
    )

    r = await client.get("/v1/admin/automations", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["error"] is None
    by_id = {w["id"]: w for w in body["workflows"]}
    assert len(by_id) == 5  # nothing is filtered out for staff

    assert by_id["w1"]["owner_kind"] == "org"
    assert by_id["w1"]["owner"] == slug
    assert by_id["w1"]["organization_name"] == "Tagged Co"
    assert by_id["w2"]["owner_kind"] == "untagged"
    assert by_id["w3"]["owner_kind"] == "internal"
    assert by_id["w4"]["owner_kind"] == "shared-template"
    # A tag matching no organization is called out rather than silently treated as an owner.
    assert by_id["w5"]["owner_kind"] == "unknown-org"

    # Unowned sorts first — the page is a to-do list for the tagging backlog.
    assert body["workflows"][0]["id"] == "w2"


async def test_automations_overview_lists_bindings(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each workflow shows which agent binds it, which is how staff spot an automation
    that is bound but no longer visible to its own org."""
    token = await _signup(client, "bindstaff@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    org = await client.post("/v1/orgs", json={"name": "Bind Co"}, headers=headers)
    org_id = org.json()["id"]
    agent = await client.post(
        "/v1/agents", json={"name": "Bind Bot"}, headers={**headers, "X-Org-Id": org_id}
    )
    # n8n tools are created by /v1/tools/n8n/bind (POST /v1/tools only accepts builtin|http),
    # and that path now needs a matching tag; the row itself is what this test is about.
    db_session.add(
        Tool(
            organization_id=uuid.UUID(org_id),
            agent_id=uuid.UUID(agent.json()["id"]),
            name="starter_automation",
            type="n8n",
            enabled=True,
            config={"workflow_id": "w9", "webhook_url": "http://n8n/webhook/x", "mode": "sync"},
            input_schema={},
        )
    )
    await db_session.flush()
    await _make_staff(db_session, "bindstaff@example.com")

    def handler(_r: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"data": [{"id": "w9", "name": "Bound Flow", "active": True, "tags": [], "nodes": []}]},
        )

    monkeypatch.setattr(
        admin_service, "get_n8n_client", lambda **_k: N8nClient("http://n8n", "k", transport=_mock(handler))
    )

    r = await client.get("/v1/admin/automations", headers=headers)
    assert r.status_code == 200, r.text
    wf = r.json()["workflows"][0]
    assert wf["owner_kind"] == "untagged"  # bound, yet invisible to the org that uses it
    assert len(wf["bindings"]) == 1
    binding = wf["bindings"][0]
    assert binding["organization_name"] == "Bind Co"
    assert binding["agent_name"] == "Bind Bot"
    assert binding["tool_name"] == "starter_automation"
    assert binding["mode"] == "sync"


async def test_automations_overview_reports_n8n_being_down(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unreachable or keyless n8n is an operational state, not a 500 — and the console
    must not render an empty table that reads as 'no automations exist'."""
    token = await _signup(client, "downstaff@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    await _make_staff(db_session, "downstaff@example.com")

    def handler(_r: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"message": "boom"})

    monkeypatch.setattr(
        admin_service, "get_n8n_client", lambda **_k: N8nClient("http://n8n", "k", transport=_mock(handler))
    )

    r = await client.get("/v1/admin/automations", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["workflows"] == []
    assert r.json()["error"]
