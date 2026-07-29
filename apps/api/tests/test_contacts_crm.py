"""The CRM lists *people* (`CrmContact`), not handles.

A person appears once we can identify them — they shared an email or phone, or an operator
added them by hand. A visitor who only ever says "hi" stays a per-channel `Contact` and
shows up in the Inbox, not here: a CRM full of `anon-9f2c` rows helps nobody.
"""

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


async def _say(client: AsyncClient, key: str, visitor: str, text: str, name: str | None = None) -> None:
    visitor_payload: dict[str, str] = {"id": visitor}
    if name:
        visitor_payload["name"] = name
    r = await client.post(
        f"/v1/public/agents/{key}/chat",
        json={"message": text, "stream": False, "visitor": visitor_payload},
    )
    assert r.status_code == 200, r.text


async def _new(client: AsyncClient, headers: dict[str, str], **fields: str) -> dict:
    body = {"display_name": "Someone", **fields}
    r = await client.post("/v1/contacts", json=body, headers=headers)
    assert r.status_code == 201, r.text
    return dict(r.json())


# ── Manual creation (the one operator-driven path in) ───────────────────────────────
async def test_create_contact_by_hand(client: AsyncClient) -> None:
    headers = await _headers(client, "crm-manual@example.com")

    created = await _new(
        client,
        headers,
        display_name="Walk-in Customer",
        email="Walkin@Example.com",
        phone="+91 98765 43210",
        lead_stage="contacted",
        order_status="Quote sent",
    )
    # Normalised on write, so a hand-typed detail matches an auto-captured one later.
    assert created["email"] == "walkin@example.com"
    assert created["phone"] == "+919876543210"
    assert created["lead_stage"] == "contacted"

    # A `manual` handle records where the person came from.
    assert [c["channel"] for c in created["channels"]] == ["manual"]
    assert created["channels"][0]["external_id"].startswith("manual-")
    assert created["conversation_count"] == 0

    listed = await client.get("/v1/contacts", headers=headers)
    assert [c["id"] for c in listed.json()["items"]] == [created["id"]]


async def test_two_manual_contacts_do_not_collide(client: AsyncClient) -> None:
    headers = await _headers(client, "crm-manual2@example.com")
    for _ in range(2):
        await _new(client, headers, display_name="Same Name")
    assert (await client.get("/v1/contacts", headers=headers)).json()["total"] == 2


async def test_manual_contact_rejects_an_unknown_lead_stage(client: AsyncClient) -> None:
    headers = await _headers(client, "crm-manual3@example.com")
    r = await client.post(
        "/v1/contacts", json={"display_name": "X", "lead_stage": "Wishlist"}, headers=headers
    )
    assert r.status_code == 422


# ── Who appears, and who doesn't ────────────────────────────────────────────────────
async def test_a_visitor_who_shares_nothing_stays_out_of_the_crm(client: AsyncClient) -> None:
    """They're still reachable in the Inbox — the CRM is for people we can identify."""
    headers = await _headers(client, "crm-anon@example.com")
    key = await _agent(client, headers)
    await _say(client, key, "v-anon", "hi, do you ship to Chennai?", name="Curious")

    assert (await client.get("/v1/contacts", headers=headers)).json()["total"] == 0


async def test_a_visitor_who_shares_an_email_appears(client: AsyncClient) -> None:
    headers = await _headers(client, "crm-shared@example.com")
    key = await _agent(client, headers)
    await _say(client, key, "v-known", "quote me please — buyer@example.com", name="Buyer")

    items = (await client.get("/v1/contacts", headers=headers)).json()["items"]
    assert len(items) == 1
    assert items[0]["email"] == "buyer@example.com"
    # The handle they used is listed against them.
    assert [c["channel"] for c in items[0]["channels"]] == ["widget"]
    assert items[0]["conversation_count"] == 1
    assert items[0]["last_active_at"]


# ── Search, filters, pagination ─────────────────────────────────────────────────────
async def test_search_matches_name_email_and_handle(client: AsyncClient) -> None:
    headers = await _headers(client, "crm-search@example.com")
    await _new(client, headers, display_name="Aadesh Kumar", email="aadesh@example.com")
    await _new(client, headers, display_name="Rohak Arya", email="rohak@example.com")

    by_name = await client.get("/v1/contacts", params={"q": "aadesh"}, headers=headers)
    assert [c["display_name"] for c in by_name.json()["items"]] == ["Aadesh Kumar"]

    by_email = await client.get("/v1/contacts", params={"q": "rohak@"}, headers=headers)
    assert [c["display_name"] for c in by_email.json()["items"]] == ["Rohak Arya"]

    # An operator searching the platform id they see in the inbox should find the person.
    handle = by_name.json()["items"][0]["channels"][0]["external_id"]
    by_handle = await client.get("/v1/contacts", params={"q": handle}, headers=headers)
    assert [c["display_name"] for c in by_handle.json()["items"]] == ["Aadesh Kumar"]


async def test_stage_label_and_channel_filters(client: AsyncClient) -> None:
    headers = await _headers(client, "crm-filter@example.com")
    person = await _new(client, headers, display_name="Filterable")
    await _new(client, headers, display_name="Other")

    await client.patch(f"/v1/contacts/{person['id']}", json={"lead_stage": "qualified"}, headers=headers)
    await client.patch(f"/v1/contacts/{person['id']}/labels", json={"labels": ["vip"]}, headers=headers)

    staged = await client.get("/v1/contacts", params={"lead_stage": "qualified"}, headers=headers)
    assert [c["id"] for c in staged.json()["items"]] == [person["id"]]
    labelled = await client.get("/v1/contacts", params={"label": "vip"}, headers=headers)
    assert [c["id"] for c in labelled.json()["items"]] == [person["id"]]

    # "People reachable on X", expressed through their handles.
    manual = await client.get("/v1/contacts", params={"channel": "manual"}, headers=headers)
    assert manual.json()["total"] == 2
    telegram = await client.get("/v1/contacts", params={"channel": "telegram"}, headers=headers)
    assert telegram.json()["items"] == []


async def test_pagination(client: AsyncClient) -> None:
    headers = await _headers(client, "crm-page@example.com")
    for i in range(5):
        await _new(client, headers, display_name=f"Person {i}")

    page = await client.get("/v1/contacts", params={"limit": 2, "offset": 0}, headers=headers)
    assert page.json()["total"] == 5
    assert len(page.json()["items"]) == 2
    rest = await client.get("/v1/contacts", params={"limit": 2, "offset": 4}, headers=headers)
    assert len(rest.json()["items"]) == 1


# ── Editing ─────────────────────────────────────────────────────────────────────────
async def test_lead_stage_is_constrained(client: AsyncClient) -> None:
    """Free text would fragment into qualified/Qualified/QUALIFIED and break the filter."""
    headers = await _headers(client, "crm-stage@example.com")
    person = await _new(client, headers)

    bad = await client.patch(
        f"/v1/contacts/{person['id']}", json={"lead_stage": "Qualified!"}, headers=headers
    )
    assert bad.status_code == 422

    ok = await client.patch(f"/v1/contacts/{person['id']}", json={"lead_stage": "customer"}, headers=headers)
    assert ok.json()["lead_stage"] == "customer"
    cleared = await client.patch(f"/v1/contacts/{person['id']}", json={"lead_stage": None}, headers=headers)
    assert cleared.json()["lead_stage"] is None


async def test_order_status_is_free_text(client: AsyncClient) -> None:
    """What counts as an order status is business-specific — don't constrain it."""
    headers = await _headers(client, "crm-order@example.com")
    person = await _new(client, headers)
    r = await client.patch(
        f"/v1/contacts/{person['id']}", json={"order_status": "Awaiting fabric #A-1"}, headers=headers
    )
    assert r.json()["order_status"] == "Awaiting fabric #A-1"


async def test_labels_are_deduplicated_and_trimmed(client: AsyncClient) -> None:
    headers = await _headers(client, "crm-labels@example.com")
    person = await _new(client, headers)
    r = await client.patch(
        f"/v1/contacts/{person['id']}/labels",
        json={"labels": [" vip ", "VIP", "", "returning"]},
        headers=headers,
    )
    assert r.json()["labels"] == ["vip", "returning"]


async def test_notes_accumulate_with_author_and_timestamp(client: AsyncClient) -> None:
    headers = await _headers(client, "crm-notes@example.com")
    person = await _new(client, headers)

    await client.post(f"/v1/contacts/{person['id']}/notes", json={"text": "Called, no answer"}, headers=headers)
    second = await client.post(
        f"/v1/contacts/{person['id']}/notes", json={"text": "Left voicemail"}, headers=headers
    )
    notes = second.json()["notes"]
    assert [n["text"] for n in notes] == ["Called, no answer", "Left voicemail"]
    assert all(n["by"] and n["at"] for n in notes)


async def test_editing_an_email_normalises_it(client: AsyncClient) -> None:
    """So a hand-typed correction still matches what auto-capture would have stored."""
    headers = await _headers(client, "crm-norm@example.com")
    person = await _new(client, headers)
    r = await client.patch(
        f"/v1/contacts/{person['id']}", json={"email": " Mixed@Case.COM "}, headers=headers
    )
    assert r.json()["email"] == "mixed@case.com"


async def test_detail_lists_conversations_across_every_linked_channel(client: AsyncClient) -> None:
    headers = await _headers(client, "crm-detail@example.com")
    key = await _agent(client, headers)
    await _say(client, key, "v-a", "reach me at multi@example.com")
    await _say(client, key, "v-b", "multi@example.com again")

    person_id = (await client.get("/v1/contacts", headers=headers)).json()["items"][0]["id"]
    detail = (await client.get(f"/v1/contacts/{person_id}", headers=headers)).json()
    assert len(detail["channels"]) == 2, "both handles should hang off one person"
    assert detail["conversation_count"] == 2
    assert len(detail["conversations"]) == 2


async def test_tenant_isolation(client: AsyncClient) -> None:
    a = await _headers(client, "crm-a@example.com", org="OrgA")
    b = await _headers(client, "crm-b@example.com", org="OrgB")
    person = await _new(client, a, display_name="Theirs")

    assert (await client.get("/v1/contacts", headers=b)).json()["items"] == []
    assert (await client.get(f"/v1/contacts/{person['id']}", headers=b)).status_code == 404
    cross = await client.patch(f"/v1/contacts/{person['id']}", json={"lead_stage": "lost"}, headers=b)
    assert cross.status_code == 404
    assert (await client.get(f"/v1/contacts/{uuid.uuid4()}", headers=a)).status_code == 404
