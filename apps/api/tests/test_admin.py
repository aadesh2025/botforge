"""Phase 17 tests: platform-staff admin console endpoints.

Staff endpoints are org-agnostic and gated by `require_staff` (user.is_staff).
Non-staff (and unauthenticated) requests must be rejected with 403.
"""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User


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
