"""Canned responses: org-scoped CRUD, shortcut hygiene, tenant isolation."""

from __future__ import annotations

from httpx import AsyncClient


async def _headers(client: AsyncClient, email: str, org: str = "CrOrg") -> dict[str, str]:
    signup = await client.post("/v1/auth/signup", json={"email": email, "password": "password123"})
    token = signup.json()["access_token"]
    o = await client.post("/v1/orgs", json={"name": org}, headers={"Authorization": f"Bearer {token}"})
    return {"Authorization": f"Bearer {token}", "X-Org-Id": o.json()["id"]}


async def test_crud_roundtrip(client: AsyncClient) -> None:
    headers = await _headers(client, "cr1@example.com")

    created = await client.post(
        "/v1/canned-responses",
        json={"shortcut": "refund", "content": "Your refund is on its way."},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    cr_id = created.json()["id"]
    assert created.json()["shortcut"] == "refund"

    listed = await client.get("/v1/canned-responses", headers=headers)
    assert [c["shortcut"] for c in listed.json()] == ["refund"]

    updated = await client.patch(
        f"/v1/canned-responses/{cr_id}", json={"content": "Refunded — 3-5 days."}, headers=headers
    )
    assert updated.json()["content"] == "Refunded — 3-5 days."

    assert (await client.delete(f"/v1/canned-responses/{cr_id}", headers=headers)).status_code == 204
    assert (await client.get("/v1/canned-responses", headers=headers)).json() == []


async def test_shortcut_is_normalized(client: AsyncClient) -> None:
    """Operators type `/refund`; storing the slash would make the picker match `//refund`."""
    headers = await _headers(client, "cr2@example.com")
    r = await client.post(
        "/v1/canned-responses", json={"shortcut": "/Refund ", "content": "x"}, headers=headers
    )
    assert r.status_code == 201, r.text
    assert r.json()["shortcut"] == "refund"


async def test_shortcut_rejects_spaces(client: AsyncClient) -> None:
    """A shortcut is matched against what's typed after `/`, which stops at whitespace."""
    headers = await _headers(client, "cr3@example.com")
    bad = await client.post(
        "/v1/canned-responses", json={"shortcut": "two words", "content": "x"}, headers=headers
    )
    assert bad.status_code == 422


async def test_custom_validator_failure_is_a_typed_422(client: AsyncClient) -> None:
    """Regression: a `field_validator` raising ValueError used to 500.

    Pydantic stores the raised exception in the error's `ctx`, which the handler then
    tried to json-encode. Any endpoint with a custom validator was affected — including
    widget-config writes, long before canned responses existed.
    """
    headers = await _headers(client, "cr-422@example.com")
    r = await client.post(
        "/v1/canned-responses", json={"shortcut": "no spaces here", "content": "x"}, headers=headers
    )
    assert r.status_code == 422, r.text
    body = r.json()
    assert body["error"]["code"] == "validation_error"
    # The reason survives serialization, so the client can show something useful.
    assert any("lowercase" in d["msg"] for d in body["error"]["details"])


async def test_duplicate_shortcut_rejected(client: AsyncClient) -> None:
    headers = await _headers(client, "cr4@example.com")
    await client.post("/v1/canned-responses", json={"shortcut": "hi", "content": "a"}, headers=headers)
    dup = await client.post(
        "/v1/canned-responses", json={"shortcut": "hi", "content": "b"}, headers=headers
    )
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "canned_responses.duplicate_shortcut"


async def test_rename_onto_an_existing_shortcut_rejected(client: AsyncClient) -> None:
    headers = await _headers(client, "cr5@example.com")
    await client.post("/v1/canned-responses", json={"shortcut": "one", "content": "a"}, headers=headers)
    second = await client.post(
        "/v1/canned-responses", json={"shortcut": "two", "content": "b"}, headers=headers
    )
    clash = await client.patch(
        f"/v1/canned-responses/{second.json()['id']}", json={"shortcut": "one"}, headers=headers
    )
    assert clash.status_code == 409

    # Renaming to its own current shortcut is a no-op, not a self-collision.
    same = await client.patch(
        f"/v1/canned-responses/{second.json()['id']}", json={"shortcut": "two"}, headers=headers
    )
    assert same.status_code == 200


async def test_search_filters_by_shortcut(client: AsyncClient) -> None:
    headers = await _headers(client, "cr6@example.com")
    for s in ("refund", "refund-late", "greeting"):
        await client.post("/v1/canned-responses", json={"shortcut": s, "content": s}, headers=headers)

    found = await client.get("/v1/canned-responses", params={"q": "ref"}, headers=headers)
    assert sorted(c["shortcut"] for c in found.json()) == ["refund", "refund-late"]

    # The composer sends what follows "/" — a leading slash must not break the match.
    with_slash = await client.get("/v1/canned-responses", params={"q": "/ref"}, headers=headers)
    assert len(with_slash.json()) == 2


async def test_tenant_isolation(client: AsyncClient) -> None:
    a = await _headers(client, "cr-a@example.com", org="OrgA")
    b = await _headers(client, "cr-b@example.com", org="OrgB")
    created = await client.post(
        "/v1/canned-responses", json={"shortcut": "secret", "content": "internal"}, headers=a
    )
    cr_id = created.json()["id"]

    assert (await client.get("/v1/canned-responses", headers=b)).json() == []
    assert (await client.get("/v1/canned-responses", headers=a)).json()[0]["id"] == cr_id
    # The same shortcut in another org is fine — uniqueness is per-org.
    assert (
        await client.post(
            "/v1/canned-responses", json={"shortcut": "secret", "content": "theirs"}, headers=b
        )
    ).status_code == 201
    cross = await client.patch(
        f"/v1/canned-responses/{cr_id}", json={"content": "hijacked"}, headers=b
    )
    assert cross.status_code == 404
