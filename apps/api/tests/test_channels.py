"""Phase 12 tests: channel signature verification + mocked inbound→bot→outbound round-trips."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels import get_channel  # importing the package registers all adapters
from app.models import Channel


def _capture_transport(calls: list[dict]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append({"url": str(request.url), "body": request.content.decode() if request.content else ""})
        return httpx.Response(200, json={"ok": True})

    return httpx.MockTransport(handler)


@pytest.fixture(autouse=True)
def _reset_transports() -> None:
    yield
    for t in ("telegram", "whatsapp", "slack", "discord"):
        ch = get_channel(t)
        if ch:
            ch.transport = None


async def _headers(client: AsyncClient, email: str = "chan@example.com") -> dict[str, str]:
    signup = await client.post("/v1/auth/signup", json={"email": email, "password": "password123"})
    token = signup.json()["access_token"]
    org = await client.post("/v1/orgs", json={"name": "ChanOrg"}, headers={"Authorization": f"Bearer {token}"})
    return {"Authorization": f"Bearer {token}", "X-Org-Id": org.json()["id"]}


async def _fake_agent(client: AsyncClient, headers: dict[str, str]) -> str:
    agent = await client.post("/v1/agents", json={"name": "Chan Bot"}, headers=headers)
    aid = agent.json()["id"]
    await client.patch(
        f"/v1/agents/{aid}/versions/1",
        json={"model_config": {"provider": "fake", "model": "fake-1"}},
        headers=headers,
    )
    return aid


# ── CRUD + secret masking ─────────────────────────────────────────────────────────
async def test_create_channel_masks_secret(client: AsyncClient) -> None:
    headers = await _headers(client)
    aid = await _fake_agent(client, headers)
    r = await client.post(
        "/v1/channels",
        json={"agent_id": aid, "type": "telegram", "config": {"bot_token": "123456:SECRET"}},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    assert r.json()["config"]["bot_token"] == "••••set"  # masked, not the raw token
    assert "/v1/channels/telegram/" in r.json()["webhook_url"]
    assert r.json()["enabled"] is False


# ── Telegram round-trip (verify → parse → bot → send) ──────────────────────────────
async def test_telegram_roundtrip(client: AsyncClient, db_session: AsyncSession) -> None:
    calls: list[dict] = []
    get_channel("telegram").transport = _capture_transport(calls)

    headers = await _headers(client, "tg@example.com")
    aid = await _fake_agent(client, headers)
    ch = await client.post(
        "/v1/channels",
        json={"agent_id": aid, "type": "telegram", "config": {"bot_token": "123:abc"}},
        headers=headers,
    )
    cid = ch.json()["id"]
    await client.post(f"/v1/channels/{cid}/enable", headers=headers)  # triggers setWebhook (mocked)

    channel = await db_session.get(Channel, uuid.UUID(cid))
    secret = channel.webhook_secret

    update = {"message": {"chat": {"id": 55}, "text": "hello telegram"}}
    good = await client.post(
        f"/v1/channels/telegram/{cid}/webhook",
        json=update,
        headers={"X-Telegram-Bot-Api-Secret-Token": secret},
    )
    assert good.status_code == 200, good.text
    send_calls = [c for c in calls if "sendMessage" in c["url"]]
    assert send_calls, "expected an outbound sendMessage"
    body = json.loads(send_calls[-1]["body"])
    assert body["chat_id"] == "55"
    assert "echo: hello telegram" in body["text"]


async def test_telegram_bad_secret_rejected(client: AsyncClient) -> None:
    get_channel("telegram").transport = _capture_transport([])
    headers = await _headers(client, "tg2@example.com")
    aid = await _fake_agent(client, headers)
    ch = await client.post(
        "/v1/channels",
        json={"agent_id": aid, "type": "telegram", "config": {"bot_token": "123:abc"}},
        headers=headers,
    )
    cid = ch.json()["id"]
    r = await client.post(
        f"/v1/channels/telegram/{cid}/webhook",
        json={"message": {"chat": {"id": 1}, "text": "hi"}},
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"},
    )
    assert r.status_code == 401


# ── WhatsApp ────────────────────────────────────────────────────────────────────────
async def test_whatsapp_verify_challenge(client: AsyncClient) -> None:
    headers = await _headers(client, "wa@example.com")
    aid = await _fake_agent(client, headers)
    ch = await client.post(
        "/v1/channels",
        json={"agent_id": aid, "type": "whatsapp", "config": {"verify_token": "vtok", "app_secret": "s"}},
        headers=headers,
    )
    cid = ch.json()["id"]
    ok = await client.get(
        f"/v1/channels/whatsapp/{cid}/webhook",
        params={"hub.mode": "subscribe", "hub.verify_token": "vtok", "hub.challenge": "CHAL123"},
    )
    assert ok.status_code == 200 and ok.text == "CHAL123"
    bad = await client.get(
        f"/v1/channels/whatsapp/{cid}/webhook",
        params={"hub.mode": "subscribe", "hub.verify_token": "nope", "hub.challenge": "x"},
    )
    assert bad.status_code == 403


async def test_whatsapp_signature_and_roundtrip(client: AsyncClient) -> None:
    calls: list[dict] = []
    get_channel("whatsapp").transport = _capture_transport(calls)
    headers = await _headers(client, "wa2@example.com")
    aid = await _fake_agent(client, headers)
    ch = await client.post(
        "/v1/channels",
        json={
            "agent_id": aid,
            "type": "whatsapp",
            "config": {"phone_number_id": "PN1", "access_token": "atok", "app_secret": "appsec"},
        },
        headers=headers,
    )
    cid = ch.json()["id"]
    await client.post(f"/v1/channels/{cid}/enable", headers=headers)

    payload = {
        "entry": [{"changes": [{"value": {"messages": [{"from": "15551234", "text": {"body": "hi wa"}}]}}]}]
    }
    body = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(b"appsec", body, hashlib.sha256).hexdigest()
    r = await client.post(
        f"/v1/channels/whatsapp/{cid}/webhook",
        content=body,
        headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"},
    )
    assert r.status_code == 200, r.text
    sends = [c for c in calls if "/PN1/messages" in c["url"]]
    assert sends and "echo: hi wa" in sends[-1]["body"]

    bad = await client.post(
        f"/v1/channels/whatsapp/{cid}/webhook", content=body, headers={"X-Hub-Signature-256": "sha256=bad"}
    )
    assert bad.status_code == 401


# ── Slack ────────────────────────────────────────────────────────────────────────────
def _slack_headers(secret: str, body: bytes) -> dict[str, str]:
    ts = str(int(time.time()))
    base = b"v0:" + ts.encode() + b":" + body
    sig = "v0=" + hmac.new(secret.encode(), base, hashlib.sha256).hexdigest()
    return {"X-Slack-Signature": sig, "X-Slack-Request-Timestamp": ts, "Content-Type": "application/json"}


async def test_slack_url_verification_and_roundtrip(client: AsyncClient) -> None:
    calls: list[dict] = []
    get_channel("slack").transport = _capture_transport(calls)
    headers = await _headers(client, "sl@example.com")
    aid = await _fake_agent(client, headers)
    ch = await client.post(
        "/v1/channels",
        json={"agent_id": aid, "type": "slack", "config": {"bot_token": "xoxb-1", "signing_secret": "ssecret"}},
        headers=headers,
    )
    cid = ch.json()["id"]
    await client.post(f"/v1/channels/{cid}/enable", headers=headers)

    challenge_body = json.dumps({"type": "url_verification", "challenge": "abc"}).encode()
    ch_resp = await client.post(
        f"/v1/channels/slack/{cid}/events", content=challenge_body, headers=_slack_headers("ssecret", challenge_body)
    )
    assert ch_resp.json()["challenge"] == "abc"

    event_body = json.dumps(
        {"type": "event_callback", "event": {"type": "app_mention", "channel": "C1", "text": "hi slack"}}
    ).encode()
    ev = await client.post(
        f"/v1/channels/slack/{cid}/events", content=event_body, headers=_slack_headers("ssecret", event_body)
    )
    assert ev.status_code == 200, ev.text
    sends = [c for c in calls if "chat.postMessage" in c["url"]]
    assert sends, "expected a chat.postMessage"
    sent = json.loads(sends[-1]["body"])
    assert sent["channel"] == "C1" and "echo: hi slack" in sent["text"]

    bad = await client.post(
        f"/v1/channels/slack/{cid}/events", content=event_body, headers=_slack_headers("wrongsecret", event_body)
    )
    assert bad.status_code == 401


# ── Discord (Ed25519 verify, PING/PONG, slash command inline reply) ─────────────────
async def test_discord_verify_and_command(client: AsyncClient) -> None:
    priv = Ed25519PrivateKey.generate()
    pub_hex = priv.public_key().public_bytes_raw().hex()

    headers = await _headers(client, "dc@example.com")
    aid = await _fake_agent(client, headers)
    ch = await client.post(
        "/v1/channels",
        json={"agent_id": aid, "type": "discord", "config": {"public_key": pub_hex}},
        headers=headers,
    )
    cid = ch.json()["id"]
    await client.post(f"/v1/channels/{cid}/enable", headers=headers)

    def signed(payload: dict) -> tuple[bytes, dict[str, str]]:
        body = json.dumps(payload).encode()
        ts = str(int(time.time()))
        sig = priv.sign(ts.encode() + body).hex()
        return body, {"X-Signature-Ed25519": sig, "X-Signature-Timestamp": ts, "Content-Type": "application/json"}

    ping_body, ping_headers = signed({"type": 1})
    pong = await client.post(f"/v1/channels/discord/{cid}/interactions", content=ping_body, headers=ping_headers)
    assert pong.json() == {"type": 1}

    cmd_body, cmd_headers = signed(
        {
            "type": 2,
            "data": {"name": "chat", "options": [{"name": "message", "value": "hi discord"}]},
            "member": {"user": {"id": "U9"}},
        }
    )
    resp = await client.post(f"/v1/channels/discord/{cid}/interactions", content=cmd_body, headers=cmd_headers)
    assert resp.json()["type"] == 4
    assert resp.json()["data"]["content"] == "echo: hi discord"

    # Tampered signature is rejected.
    bad = await client.post(
        f"/v1/channels/discord/{cid}/interactions",
        content=ping_body,
        headers={**ping_headers, "X-Signature-Ed25519": "00" * 64},
    )
    assert bad.status_code == 401
