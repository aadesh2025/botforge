"""Contacts CRM: listing, segmentation, and operator annotations."""

from __future__ import annotations

import uuid

from httpx import AsyncClient


async def _headers(client: AsyncClient, email: str, org: str = "CrmOrg") -> dict[str, str]:
    signup = await client.post("/v1/auth/signup", json={"email": email, "password": "password123"})
    token = signup.json()["access_token"]
    o = await client.post("/v1/orgs", json={"name": org}, headers={"Authorization": f"Bearer {token}"})
    return {"Authorization": f"Bearer {token}", "X-Org-Id": o.json()["id"]}


async def _agent(client: AsyncClient, headers: dict[str, str]) -> str:
    agent = await client.post("/v1/agents", json={"name": "CRM Bot"}, headers=headers)
    aid = agent.json()["id"]
    await client.patch(
        f"/v1/agents/{aid}/versions/1",
        json={"model_config": {"provider": "fake", "model": "fake-1"}},
        headers=headers,
    )
    return str(agent.json()["public_key"])


async def _visitor(client: AsyncClient, key: str, visitor_id: str, name: str, message: str = "hi") -> None:
    r = await client.post(
        f"/v1/public/agents/{key}/chat",
        json={"message": message, "stream": False, "visitor": {"id": visitor_id, "name": name}},
    )
    assert r.status_code == 200, r.text


async def test_list_reflects_contacts_created_by_conversations(client: AsyncClient) -> None:
    headers = await _headers(client, "crm1@example.com")
    key = await _agent(client, headers)
    await _visitor(client, key, "v-1", "Aadesh")
    await _visitor(client, key, "v-2", "Rohak")

    listed = await client.get("/v1/contacts", headers=headers)
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert body["total"] == 2
    names = sorted(c["display_name"] for c in body["items"])
    assert names == ["Aadesh", "Rohak"]
    # Activity is derived from the linked conversations, not stored twice.
    assert all(c["conversation_count"] == 1 and c["last_active_at"] for c in body["items"])


async def test_search_and_filters(client: AsyncClient) -> None:
    headers = await _headers(client, "crm2@example.com")
    key = await _agent(client, headers)
    await _visitor(client, key, "v-aa", "Aadesh Kumar")
    await _visitor(client, key, "v-bb", "Rohak Arya")

    by_name = await client.get("/v1/contacts", params={"q": "aadesh"}, headers=headers)
    assert [c["display_name"] for c in by_name.json()["items"]] == ["Aadesh Kumar"]

    # Searching the platform id matters when there's no name — e.g. a phone number.
    by_id = await client.get("/v1/contacts", params={"q": "v-bb"}, headers=headers)
    assert [c["display_name"] for c in by_id.json()["items"]] == ["Rohak Arya"]

    cid = by_name.json()["items"][0]["id"]
    await client.patch(f"/v1/contacts/{cid}", json={"lead_stage": "qualified"}, headers=headers)
    await client.patch(f"/v1/contacts/{cid}/labels", json={"labels": ["vip"]}, headers=headers)

    staged = await client.get("/v1/contacts", params={"lead_stage": "qualified"}, headers=headers)
    assert [c["id"] for c in staged.json()["items"]] == [cid]
    labelled = await client.get("/v1/contacts", params={"label": "vip"}, headers=headers)
    assert [c["id"] for c in labelled.json()["items"]] == [cid]
    by_channel = await client.get("/v1/contacts", params={"channel": "telegram"}, headers=headers)
    assert by_channel.json()["items"] == []


async def test_pagination(client: AsyncClient) -> None:
    headers = await _headers(client, "crm3@example.com")
    key = await _agent(client, headers)
    for i in range(5):
        await _visitor(client, key, f"v-{i}", f"Person {i}")

    page = await client.get("/v1/contacts", params={"limit": 2, "offset": 0}, headers=headers)
    assert page.json()["total"] == 5
    assert len(page.json()["items"]) == 2

    rest = await client.get("/v1/contacts", params={"limit": 2, "offset": 4}, headers=headers)
    assert len(rest.json()["items"]) == 1


async def test_detail_lists_linked_conversations(client: AsyncClient) -> None:
    headers = await _headers(client, "crm4@example.com")
    key = await _agent(client, headers)
    await _visitor(client, key, "v-multi", "Repeat Customer", "first")
    await _visitor(client, key, "v-multi", "Repeat Customer", "second")

    cid = (await client.get("/v1/contacts", headers=headers)).json()["items"][0]["id"]
    detail = await client.get(f"/v1/contacts/{cid}", headers=headers)
    assert detail.status_code == 200, detail.text
    # Same visitor id ⇒ one contact; each chat call without a conversation_id starts a thread.
    assert detail.json()["conversation_count"] == 2
    assert len(detail.json()["conversations"]) == 2


async def test_lead_stage_is_constrained(client: AsyncClient) -> None:
    """Free text would fragment into qualified/Qualified/QUALIFIED and break the filter."""
    headers = await _headers(client, "crm5@example.com")
    key = await _agent(client, headers)
    await _visitor(client, key, "v-x", "X")
    cid = (await client.get("/v1/contacts", headers=headers)).json()["items"][0]["id"]

    bad = await client.patch(f"/v1/contacts/{cid}", json={"lead_stage": "Qualified!"}, headers=headers)
    assert bad.status_code == 422

    ok = await client.patch(f"/v1/contacts/{cid}", json={"lead_stage": "customer"}, headers=headers)
    assert ok.json()["lead_stage"] == "customer"
    # Clearing it back to "no stage" is allowed.
    cleared = await client.patch(f"/v1/contacts/{cid}", json={"lead_stage": None}, headers=headers)
    assert cleared.json()["lead_stage"] is None


async def test_labels_are_deduplicated_and_trimmed(client: AsyncClient) -> None:
    headers = await _headers(client, "crm6@example.com")
    key = await _agent(client, headers)
    await _visitor(client, key, "v-l", "L")
    cid = (await client.get("/v1/contacts", headers=headers)).json()["items"][0]["id"]

    r = await client.patch(
        f"/v1/contacts/{cid}/labels",
        json={"labels": [" vip ", "VIP", "", "returning"]},
        headers=headers,
    )
    assert r.json()["labels"] == ["vip", "returning"]


async def test_notes_accumulate_with_author_and_timestamp(client: AsyncClient) -> None:
    headers = await _headers(client, "crm7@example.com")
    key = await _agent(client, headers)
    await _visitor(client, key, "v-n", "N")
    cid = (await client.get("/v1/contacts", headers=headers)).json()["items"][0]["id"]

    await client.post(f"/v1/contacts/{cid}/notes", json={"text": "Called, no answer"}, headers=headers)
    second = await client.post(
        f"/v1/contacts/{cid}/notes", json={"text": "Left voicemail"}, headers=headers
    )
    notes = second.json()["notes"]
    assert [n["text"] for n in notes] == ["Called, no answer", "Left voicemail"]
    assert all(n["by"] and n["at"] for n in notes)


async def test_order_status_is_free_text(client: AsyncClient) -> None:
    """What counts as an order status is business-specific — don't constrain it."""
    headers = await _headers(client, "crm8@example.com")
    key = await _agent(client, headers)
    await _visitor(client, key, "v-o", "O")
    cid = (await client.get("/v1/contacts", headers=headers)).json()["items"][0]["id"]

    r = await client.patch(
        f"/v1/contacts/{cid}", json={"order_status": "Awaiting fabric #A-1"}, headers=headers
    )
    assert r.json()["order_status"] == "Awaiting fabric #A-1"


async def test_tenant_isolation(client: AsyncClient) -> None:
    a = await _headers(client, "crm-a@example.com", org="OrgA")
    b = await _headers(client, "crm-b@example.com", org="OrgB")
    key = await _agent(client, a)
    await _visitor(client, key, "v-secret", "Theirs")
    cid = (await client.get("/v1/contacts", headers=a)).json()["items"][0]["id"]

    assert (await client.get("/v1/contacts", headers=b)).json()["items"] == []
    assert (await client.get(f"/v1/contacts/{cid}", headers=b)).status_code == 404
    cross = await client.patch(f"/v1/contacts/{cid}", json={"lead_stage": "lost"}, headers=b)
    assert cross.status_code == 404
    assert (await client.get(f"/v1/contacts/{uuid.uuid4()}", headers=a)).status_code == 404


# ── Manual creation (the one operator-driven path into this table) ──────────────────
async def test_create_contact_by_hand(client: AsyncClient) -> None:
    headers = await _headers(client, "crm-manual@example.com")

    created = await client.post(
        "/v1/contacts",
        json={
            "display_name": "Walk-in Customer",
            "email": "walkin@example.com",
            "phone": "+91 98765 43210",
            "lead_stage": "contacted",
            "order_status": "Quote sent",
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["display_name"] == "Walk-in Customer"
    assert body["channel"] == "manual"
    # A synthetic id keeps (org, channel, external_id) uniqueness meaningful.
    assert body["external_id"].startswith("manual-")
    assert body["extra"]["email"] == "walkin@example.com"
    assert body["lead_stage"] == "contacted"
    assert body["conversation_count"] == 0

    listed = await client.get("/v1/contacts", headers=headers)
    assert [c["id"] for c in listed.json()["items"]] == [body["id"]]


async def test_two_manual_contacts_do_not_collide(client: AsyncClient) -> None:
    """Same name, no platform id — the generated external_id has to keep them distinct."""
    headers = await _headers(client, "crm-manual2@example.com")
    for _ in range(2):
        r = await client.post("/v1/contacts", json={"display_name": "Same Name"}, headers=headers)
        assert r.status_code == 201, r.text
    assert (await client.get("/v1/contacts", headers=headers)).json()["total"] == 2


async def test_manual_contact_rejects_an_unknown_lead_stage(client: AsyncClient) -> None:
    headers = await _headers(client, "crm-manual3@example.com")
    r = await client.post(
        "/v1/contacts", json={"display_name": "X", "lead_stage": "Wishlist"}, headers=headers
    )
    assert r.status_code == 422


async def test_manual_contacts_are_filterable_like_any_other(client: AsyncClient) -> None:
    headers = await _headers(client, "crm-manual4@example.com")
    await client.post(
        "/v1/contacts", json={"display_name": "Manual Lead", "lead_stage": "qualified"}, headers=headers
    )
    by_channel = await client.get("/v1/contacts", params={"channel": "manual"}, headers=headers)
    assert [c["display_name"] for c in by_channel.json()["items"]] == ["Manual Lead"]
    by_stage = await client.get("/v1/contacts", params={"lead_stage": "qualified"}, headers=headers)
    assert len(by_stage.json()["items"]) == 1
