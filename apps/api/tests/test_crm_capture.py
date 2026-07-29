"""Auto-capture: the regex gate, identity resolution, and the org toggle.

The gate is the point of the design — most messages contain no contact details, and running
an LLM over every turn to find that out would cost real money for nothing. Several tests
below assert the model is *not* called.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crm import extract as crm_extract
from app.crm.extract import ExtractedContact, find_contact_hints, normalize_email, normalize_phone
from app.models import Contact, CrmContact, Organization


@pytest.fixture
def llm_calls(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record every extraction call and answer deterministically, with no real provider."""
    calls: list[str] = []

    async def _fake(_session: object, _org: uuid.UUID, text: str, hints: object) -> ExtractedContact:
        calls.append(text)
        h = find_contact_hints(text)
        name = None
        for marker in ("i'm ", "i am ", "this is ", "name is "):
            if marker in text.lower():
                after = text.lower().split(marker, 1)[1]
                name = after.split(",")[0].split(".")[0].split(" and ")[0].strip().title()[:255]
                break
        return ExtractedContact(name=name or None, email=normalize_email(h.email), phone=h.phone)

    monkeypatch.setattr(crm_extract, "extract_contact", _fake)
    # capture.py imported the symbol directly, so patch it there too.
    from app.crm import capture as crm_capture

    monkeypatch.setattr(crm_capture, "extract_contact", _fake)
    return calls


async def _headers(client: AsyncClient, email: str) -> dict[str, str]:
    signup = await client.post("/v1/auth/signup", json={"email": email, "password": "password123"})
    token = signup.json()["access_token"]
    o = await client.post("/v1/orgs", json={"name": "CapOrg"}, headers={"Authorization": f"Bearer {token}"})
    return {"Authorization": f"Bearer {token}", "X-Org-Id": o.json()["id"]}


async def _agent(client: AsyncClient, headers: dict[str, str]) -> str:
    agent = await client.post("/v1/agents", json={"name": "Cap Bot"}, headers=headers)
    aid = agent.json()["id"]
    await client.patch(
        f"/v1/agents/{aid}/versions/1",
        json={"model_config": {"provider": "fake", "model": "fake-1"}},
        headers=headers,
    )
    return str(agent.json()["public_key"])


async def _say(client: AsyncClient, key: str, visitor: str, text: str, name: str = "Visitor") -> None:
    r = await client.post(
        f"/v1/public/agents/{key}/chat",
        json={"message": text, "stream": False, "visitor": {"id": visitor, "name": name}},
    )
    assert r.status_code == 200, r.text


async def _people(session: AsyncSession, headers: dict[str, str]) -> list[CrmContact]:
    """Scoped to the org under test — every query in this codebase is, and the DB also
    holds rows the 0013 migration backfilled."""
    org_id = uuid.UUID(headers["X-Org-Id"])
    stmt = select(CrmContact).where(CrmContact.organization_id == org_id)
    return list((await session.execute(stmt)).scalars().all())


# ── The cheap gate ───────────────────────────────────────────────────────────────
def test_hints_find_emails_and_phones() -> None:
    assert find_contact_hints("mail me at Bob@Example.COM").email == "Bob@Example.COM"
    assert find_contact_hints("call +91 98765 43210").phone == "+919876543210"
    assert find_contact_hints("ring 555-0123-99").phone == "5550123 99".replace(" ", "")


def test_hints_ignore_ordinary_messages() -> None:
    for text in ("hello there", "what are your hours?", "I need help with order 42"):
        assert not find_contact_hints(text).any(), text


def test_an_email_local_part_is_not_read_as_a_phone() -> None:
    hints = find_contact_hints("write to 918887776665@example.com")
    assert hints.email == "918887776665@example.com"
    assert hints.phone is None


def test_normalisation_makes_the_same_value_match_itself() -> None:
    assert normalize_email(" Bob@Example.COM ") == "bob@example.com"
    assert normalize_email("not-an-email") is None
    # The same number, written three ways.
    assert normalize_phone("+91 98765 43210") == normalize_phone("+91-98765-43210") == "+919876543210"
    assert normalize_phone("(+91) 98765.43210") == "+919876543210"
    assert normalize_phone("12345") is None  # too short to be real


async def test_no_llm_call_when_nothing_contact_shaped_is_present(
    client: AsyncClient, llm_calls: list[str], db_session: AsyncSession
) -> None:
    """The whole reason for the regex gate — this is the common case."""
    headers = await _headers(client, "cap-gate@example.com")
    key = await _agent(client, headers)

    for text in ("hi there", "do you ship to Chennai?", "thanks!"):
        await _say(client, key, "v-gate", text)

    assert llm_calls == [], "the model was called for a message with no contact details"
    assert await _people(db_session, headers) == []


async def test_an_email_triggers_capture(
    client: AsyncClient, llm_calls: list[str], db_session: AsyncSession
) -> None:
    headers = await _headers(client, "cap-email@example.com")
    key = await _agent(client, headers)
    await _say(client, key, "v-e", "I'm Aadesh, reach me at Aadesh@Example.com")

    assert len(llm_calls) == 1
    people = await _people(db_session, headers)
    assert len(people) == 1
    assert people[0].email == "aadesh@example.com"  # normalised on the way in
    assert people[0].display_name == "Aadesh"


# ── Identity resolution ──────────────────────────────────────────────────────────
async def test_the_same_email_on_two_channels_is_one_person(
    client: AsyncClient, llm_calls: list[str], db_session: AsyncSession
) -> None:
    """The headline behaviour: recognise a returning customer on a new channel."""
    headers = await _headers(client, "cap-cross@example.com")
    key = await _agent(client, headers)

    await _say(client, key, "v-web", "I'm Rohak, my email is rohak@example.com")
    # A different visitor id is a different `Contact` — a different channel identity.
    await _say(client, key, "v-other", "hello again, rohak@example.com here")

    people = await _people(db_session, headers)
    assert len(people) == 1, "the same email arriving twice must not create two people"

    linked = (
        (await db_session.execute(select(Contact).where(Contact.crm_contact_id == people[0].id)))
        .scalars()
        .all()
    )
    assert {c.external_id for c in linked} == {"v-web", "v-other"}


async def test_matching_is_by_phone_too(
    client: AsyncClient, llm_calls: list[str], db_session: AsyncSession
) -> None:
    headers = await _headers(client, "cap-phone@example.com")
    key = await _agent(client, headers)
    await _say(client, key, "v-p1", "call me on +91 98765 43210")
    # Same number, written differently — normalisation is what makes this match.
    await _say(client, key, "v-p2", "hi, this is +91-98765-43210")

    assert len(await _people(db_session, headers)) == 1


async def test_matching_is_never_by_name(
    client: AsyncClient, llm_calls: list[str], db_session: AsyncSession
) -> None:
    """Two different customers who happen to share a name must stay separate.

    Merging them would silently mix two people's histories — far worse than a duplicate.
    """
    headers = await _headers(client, "cap-name@example.com")
    key = await _agent(client, headers)
    await _say(client, key, "v-n1", "I'm Alex, alex.one@example.com")
    await _say(client, key, "v-n2", "I'm Alex, alex.two@example.com")

    people = await _people(db_session, headers)
    assert len(people) == 2
    assert {p.email for p in people} == {"alex.one@example.com", "alex.two@example.com"}


async def test_a_later_message_fills_in_a_missing_detail(
    client: AsyncClient, llm_calls: list[str], db_session: AsyncSession
) -> None:
    headers = await _headers(client, "cap-learn@example.com")
    key = await _agent(client, headers)

    # An anonymous visitor: no name anywhere yet, so there's a blank to fill.
    first = await client.post(
        f"/v1/public/agents/{key}/chat",
        json={"message": "reach me at learner@example.com", "stream": False, "visitor": {"id": "v-l"}},
    )
    assert first.status_code == 200, first.text
    people = await _people(db_session, headers)
    assert people[0].display_name is None

    await _say(client, key, "v-l", "I'm Priya, learner@example.com")
    await db_session.refresh(people[0])
    assert people[0].display_name == "Priya"
    assert len(await _people(db_session, headers)) == 1


async def test_a_known_detail_is_not_overwritten_by_a_later_guess(
    client: AsyncClient, llm_calls: list[str], db_session: AsyncSession
) -> None:
    """Fill blanks, don't overwrite. An operator may have corrected the name by hand, and a
    later message shouldn't quietly undo that."""
    headers = await _headers(client, "cap-keep@example.com")
    key = await _agent(client, headers)
    await _say(client, key, "v-k", "keeper@example.com", name="Known Name")

    people = await _people(db_session, headers)
    assert people[0].display_name == "Known Name"

    await _say(client, key, "v-k", "I'm Someone Else, keeper@example.com")
    await db_session.refresh(people[0])
    assert people[0].display_name == "Known Name"


# ── The toggle ───────────────────────────────────────────────────────────────────
async def test_the_toggle_off_skips_extraction_entirely(
    client: AsyncClient, llm_calls: list[str], db_session: AsyncSession
) -> None:
    headers = await _headers(client, "cap-off@example.com")
    key = await _agent(client, headers)

    org = (await db_session.execute(select(Organization).where(Organization.name == "CapOrg"))).scalars().first()
    assert org is not None
    assert org.auto_crm_capture_enabled is True, "capture should default on"
    org.auto_crm_capture_enabled = False
    await db_session.flush()

    await _say(client, key, "v-off", "I'm Sam, sam@example.com, +91 98765 43210")

    assert llm_calls == [], "extraction ran despite the toggle being off"
    assert await _people(db_session, headers) == []


async def test_the_toggle_is_settable_through_the_api(client: AsyncClient) -> None:
    headers = await _headers(client, "cap-toggle@example.com")
    org_id = headers["X-Org-Id"]
    assert (await client.get(f"/v1/orgs/{org_id}", headers=headers)).json()["auto_crm_capture_enabled"] is True

    off = await client.patch(
        f"/v1/orgs/{org_id}", json={"auto_crm_capture_enabled": False}, headers=headers
    )
    assert off.status_code == 200, off.text
    assert off.json()["auto_crm_capture_enabled"] is False


# ── The inbox reads through the link ─────────────────────────────────────────────
async def test_the_inbox_shows_the_crm_name_on_a_new_channel(
    client: AsyncClient, llm_calls: list[str], db_session: AsyncSession
) -> None:
    """A recognised returning customer appears as themselves, not as a raw handle."""
    headers = await _headers(client, "cap-inbox@example.com")
    agent = await client.post("/v1/agents", json={"name": "Inbox Cap"}, headers=headers)
    aid, key = agent.json()["id"], agent.json()["public_key"]
    await client.patch(
        f"/v1/agents/{aid}/versions/1",
        json={
            "fallback_message": "Connecting you to a teammate now.",
            "model_config": {"provider": "fake", "model": "fake-1"},
            "features": {"tools_enabled": False, "memory_enabled": True, "handoff_enabled": True},
        },
        headers=headers,
    )

    await _say(client, key, "v-known", "I'm Meera, meera@example.com", name="anon")
    # A brand-new handle, same email, and this one escalates to a human.
    r = await client.post(
        f"/v1/public/agents/{key}/chat",
        json={
            "message": "meera@example.com — I want a human agent",
            "stream": False,
            "visitor": {"id": "v-fresh"},
        },
    )
    assert r.status_code == 200, r.text

    items = (await client.get("/v1/inbox/conversations", headers=headers)).json()
    assert items, "the escalated conversation should be queued"
    assert items[0]["contact"]["display_name"] == "Meera"
    assert items[0]["contact"]["crm_contact_id"] is not None
