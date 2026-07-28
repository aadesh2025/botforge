"""Contact identity + the Meta DM adapters (Instagram / Facebook Messenger).

Covers the promise the unified inbox rests on: every inbound message resolves to a
Contact, the conversation points at it, and the inbox hands the operator a name and an
avatar instead of a raw platform id.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from collections.abc import Iterator

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels import get_channel  # importing the package registers all adapters
from app.models import Contact, Conversation


@pytest.fixture(autouse=True)
def _reset_transports() -> Iterator[None]:
    yield
    for t in ("telegram", "whatsapp", "instagram", "facebook"):
        adapter = get_channel(t)
        if adapter:
            adapter.transport = None


def _graph_transport(calls: list[dict], profile: dict | None = None) -> httpx.MockTransport:
    """Stands in for the Graph API: profile GETs answer with `profile`, sends 200 OK."""

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append({"method": request.method, "url": str(request.url), "body": request.content.decode()})
        if request.method == "GET":
            if profile is None:
                return httpx.Response(400, json={"error": {"message": "no permission"}})
            return httpx.Response(200, json=profile)
        return httpx.Response(200, json={"ok": True})

    return httpx.MockTransport(handler)


async def _headers(client: AsyncClient, email: str) -> dict[str, str]:
    signup = await client.post("/v1/auth/signup", json={"email": email, "password": "password123"})
    token = signup.json()["access_token"]
    org = await client.post("/v1/orgs", json={"name": "ContactOrg"}, headers={"Authorization": f"Bearer {token}"})
    return {"Authorization": f"Bearer {token}", "X-Org-Id": org.json()["id"]}


async def _fake_agent(client: AsyncClient, headers: dict[str, str], *, handoff: bool = False) -> str:
    agent = await client.post("/v1/agents", json={"name": "Contact Bot"}, headers=headers)
    aid = agent.json()["id"]
    await client.patch(
        f"/v1/agents/{aid}/versions/1",
        json={
            "model_config": {"provider": "fake", "model": "fake-1"},
            "features": {"tools_enabled": False, "memory_enabled": True, "handoff_enabled": handoff},
        },
        headers=headers,
    )
    return aid


async def _connect(
    client: AsyncClient, headers: dict[str, str], aid: str, ctype: str, config: dict
) -> str:
    ch = await client.post(
        "/v1/channels", json={"agent_id": aid, "type": ctype, "config": config}, headers=headers
    )
    assert ch.status_code == 201, ch.text
    cid = ch.json()["id"]
    await client.post(f"/v1/channels/{cid}/enable", headers=headers)
    return cid


def _signed(payload: dict, secret: str) -> tuple[bytes, dict[str, str]]:
    body = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return body, {"X-Hub-Signature-256": sig, "Content-Type": "application/json"}


def _ig_payload(sender: str, text: str, obj: str = "instagram") -> dict:
    return {
        "object": obj,
        "entry": [{"id": "PAGE1", "messaging": [{"sender": {"id": sender}, "message": {"text": text}}]}],
    }


async def _contact_for(session: AsyncSession, channel: str, external_id: str) -> Contact | None:
    stmt = select(Contact).where(Contact.channel == channel, Contact.external_id == external_id)
    return (await session.execute(stmt)).scalar_one_or_none()


# ── Telegram: identity comes straight off the update, no lookup ─────────────────────
async def test_telegram_inbound_creates_contact(client: AsyncClient, db_session: AsyncSession) -> None:
    get_channel("telegram").transport = _graph_transport([])
    headers = await _headers(client, "tgc@example.com")
    aid = await _fake_agent(client, headers)
    cid = await _connect(client, headers, aid, "telegram", {"bot_token": "123:abc"})
    channel = (await client.get(f"/v1/channels/{cid}", headers=headers)).json()

    await client.post(
        f"/v1/channels/telegram/{cid}/webhook",
        json={
            "message": {
                "chat": {"id": 900},
                "from": {"id": 900, "first_name": "Aadesh", "last_name": "S", "username": "aadeshx"},
                "text": "hello",
            }
        },
        headers={"X-Telegram-Bot-Api-Secret-Token": channel["webhook_secret"]},
    )

    contact = await _contact_for(db_session, "telegram", "900")
    assert contact is not None
    assert contact.display_name == "Aadesh S"
    assert contact.extra["username"] == "aadeshx"
    # Telegram photo URLs embed the bot token, so we deliberately don't store one.
    assert contact.avatar_url is None

    conv = (
        await db_session.execute(select(Conversation).where(Conversation.channel_user_id == "900"))
    ).scalar_one()
    assert conv.contact_id == contact.id


async def test_contact_refreshes_but_never_blanks(client: AsyncClient, db_session: AsyncSession) -> None:
    """A later message with a new name wins; one with no name leaves the name alone."""
    get_channel("telegram").transport = _graph_transport([])
    headers = await _headers(client, "tgc2@example.com")
    aid = await _fake_agent(client, headers)
    cid = await _connect(client, headers, aid, "telegram", {"bot_token": "123:abc"})
    secret = (await client.get(f"/v1/channels/{cid}", headers=headers)).json()["webhook_secret"]
    hook = {"X-Telegram-Bot-Api-Secret-Token": secret}

    async def send(from_obj: dict, text: str) -> None:
        await client.post(
            f"/v1/channels/telegram/{cid}/webhook",
            json={"message": {"chat": {"id": 901}, "from": from_obj, "text": text}},
            headers=hook,
        )

    await send({"id": 901, "first_name": "Old"}, "one")
    await send({"id": 901, "first_name": "New", "last_name": "Name"}, "two")
    contact = await _contact_for(db_session, "telegram", "901")
    assert contact is not None and contact.display_name == "New Name"

    await send({"id": 901}, "three")  # anonymous payload shape
    await db_session.refresh(contact)
    assert contact.display_name == "New Name", "a nameless payload must not erase a known name"


# ── Instagram: signature, Graph profile lookup, send ────────────────────────────────
async def test_instagram_roundtrip_with_profile(client: AsyncClient, db_session: AsyncSession) -> None:
    calls: list[dict] = []
    get_channel("instagram").transport = _graph_transport(
        calls, profile={"id": "IG42", "name": "Aadesh", "username": "_.aadesx._", "profile_pic": "https://cdn/x.jpg"}
    )
    headers = await _headers(client, "ig@example.com")
    aid = await _fake_agent(client, headers)
    cid = await _connect(
        client, headers, aid, "instagram", {"page_access_token": "igtok", "app_secret": "sec", "verify_token": "vt"}
    )

    body, sig_headers = _signed(_ig_payload("IG42", "what service do u provide"), "sec")
    ok = await client.post(f"/v1/channels/instagram/{cid}/webhook", content=body, headers=sig_headers)
    assert ok.status_code == 200, ok.text

    contact = await _contact_for(db_session, "instagram", "IG42")
    assert contact is not None
    assert contact.display_name == "Aadesh"
    assert contact.avatar_url == "https://cdn/x.jpg"
    assert contact.extra["username"] == "_.aadesx._"

    sends = [c for c in calls if c["method"] == "POST" and "/me/messages" in c["url"]]
    assert sends, "expected an outbound Send API call"
    sent = json.loads(sends[-1]["body"])
    assert sent["recipient"]["id"] == "IG42"
    assert "echo: what service do u provide" in sent["message"]["text"]

    bad = await client.post(
        f"/v1/channels/instagram/{cid}/webhook", content=body, headers={"X-Hub-Signature-256": "sha256=bad"}
    )
    assert bad.status_code == 401


async def test_instagram_profile_fetched_once(client: AsyncClient) -> None:
    """A chatty thread must not hit the Graph API on every message."""
    calls: list[dict] = []
    ig_profile = {"id": "IG7", "name": "Rohak", "profile_pic": "https://cdn/r.jpg"}
    get_channel("instagram").transport = _graph_transport(calls, profile=ig_profile)
    headers = await _headers(client, "ig2@example.com")
    aid = await _fake_agent(client, headers)
    cid = await _connect(client, headers, aid, "instagram", {"page_access_token": "t", "app_secret": "sec"})

    for text in ("hi", "still there?", "hello?"):
        body, sig_headers = _signed(_ig_payload("IG7", text), "sec")
        await client.post(f"/v1/channels/instagram/{cid}/webhook", content=body, headers=sig_headers)

    profile_gets = [c for c in calls if c["method"] == "GET"]
    assert len(profile_gets) == 1, f"expected one profile lookup, got {len(profile_gets)}"


async def test_meta_challenge_and_object_isolation(client: AsyncClient, db_session: AsyncSession) -> None:
    """Both Meta surfaces do the hub.challenge handshake, and neither eats the other's events."""
    fb_profile = {"id": "PS1", "first_name": "Brennan", "last_name": "Wells"}
    get_channel("facebook").transport = _graph_transport([], profile=fb_profile)
    headers = await _headers(client, "fb@example.com")
    aid = await _fake_agent(client, headers)
    cid = await _connect(
        client, headers, aid, "facebook", {"page_access_token": "pt", "app_secret": "sec", "verify_token": "vtok"}
    )

    ok = await client.get(
        f"/v1/channels/facebook/{cid}/webhook",
        params={"hub.mode": "subscribe", "hub.verify_token": "vtok", "hub.challenge": "CH1"},
    )
    assert ok.status_code == 200 and ok.text == "CH1"
    bad = await client.get(
        f"/v1/channels/facebook/{cid}/webhook",
        params={"hub.mode": "subscribe", "hub.verify_token": "nope", "hub.challenge": "CH1"},
    )
    assert bad.status_code == 403

    # An Instagram-shaped delivery to the Messenger webhook is ignored, not mis-attributed.
    body, sig_headers = _signed(_ig_payload("PS1", "hi", obj="instagram"), "sec")
    await client.post(f"/v1/channels/facebook/{cid}/webhook", content=body, headers=sig_headers)
    assert await _contact_for(db_session, "facebook", "PS1") is None

    body, sig_headers = _signed(_ig_payload("PS1", "hi there", obj="page"), "sec")
    assert (
        await client.post(f"/v1/channels/facebook/{cid}/webhook", content=body, headers=sig_headers)
    ).status_code == 200
    contact = await _contact_for(db_session, "facebook", "PS1")
    assert contact is not None and contact.display_name == "Brennan Wells"


async def test_meta_echo_and_read_receipts_ignored(client: AsyncClient) -> None:
    adapter = get_channel("instagram")
    channel = type("C", (), {"id": uuid.uuid4(), "config": {}})()
    receipt = {"object": "instagram", "entry": [{"messaging": [{"read": {"mid": "m"}}]}]}
    assert adapter.parse_inbound(channel, receipt) is None
    echo = {
        "object": "instagram",
        "entry": [{"messaging": [{"sender": {"id": "PAGE"}, "message": {"text": "ours", "is_echo": True}}]}],
    }
    assert adapter.parse_inbound(channel, echo) is None


async def test_missing_token_does_not_raise(client: AsyncClient) -> None:
    """Per CLAUDE.md §7: no credentials → warn and carry on, never 500 the webhook."""
    get_channel("instagram").transport = _graph_transport([])
    headers = await _headers(client, "ig3@example.com")
    aid = await _fake_agent(client, headers)
    cid = await _connect(client, headers, aid, "instagram", {"app_secret": "sec"})  # no page token

    body, sig_headers = _signed(_ig_payload("IG9", "hi"), "sec")
    resp = await client.post(f"/v1/channels/instagram/{cid}/webhook", content=body, headers=sig_headers)
    assert resp.status_code == 200


# ── Inbox surface: contact payload + per-channel filter ────────────────────────────
async def test_inbox_exposes_contact_and_filters_by_channel(client: AsyncClient) -> None:
    ig_profile = {"id": "IG5", "name": "Matthew Segura", "profile_pic": "https://cdn/m.jpg"}
    get_channel("instagram").transport = _graph_transport([], profile=ig_profile)
    headers = await _headers(client, "inbox-ct@example.com")
    aid = await _fake_agent(client, headers, handoff=True)
    cid = await _connect(client, headers, aid, "instagram", {"page_access_token": "t", "app_secret": "sec"})

    # A handoff is what puts a conversation in the operator queue.
    body, sig_headers = _signed(_ig_payload("IG5", "can I talk to a human please?"), "sec")
    assert (
        await client.post(f"/v1/channels/instagram/{cid}/webhook", content=body, headers=sig_headers)
    ).status_code == 200

    items = (await client.get("/v1/inbox/conversations", headers=headers)).json()
    item = next(i for i in items if i["channel"] == "instagram")
    assert item["contact"]["display_name"] == "Matthew Segura"
    assert item["contact"]["avatar_url"] == "https://cdn/m.jpg"

    detail = (await client.get(f"/v1/inbox/conversations/{item['id']}", headers=headers)).json()
    assert detail["contact"]["display_name"] == "Matthew Segura"

    scoped = await client.get("/v1/inbox/conversations", params={"channel": "instagram"}, headers=headers)
    assert [i["id"] for i in scoped.json()] == [item["id"]]
    empty = await client.get("/v1/inbox/conversations", params={"channel": "whatsapp"}, headers=headers)
    assert empty.json() == []


async def test_widget_visitor_becomes_a_contact(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _headers(client, "wgt@example.com")
    agent = await client.post("/v1/agents", json={"name": "Widget Bot"}, headers=headers)
    aid, key = agent.json()["id"], agent.json()["public_key"]
    await client.patch(
        f"/v1/agents/{aid}/versions/1",
        json={"model_config": {"provider": "fake", "model": "fake-1"}},
        headers=headers,
    )

    r = await client.post(
        f"/v1/public/agents/{key}/chat",
        json={"message": "hi", "stream": False, "visitor": {"id": "v-123", "name": "Tom", "email": "tom@x.com"}},
    )
    assert r.status_code == 200, r.text

    contact = await _contact_for(db_session, "widget", "v-123")
    assert contact is not None
    assert contact.display_name == "Tom"
    assert contact.extra["email"] == "tom@x.com"
