"""The attention queue, end to end (docs/11 §L6, Phase E).

The distinction this file exists to pin: **attention is not handoff.** On `elevated` the bot
keeps answering while a human is alerted; only `crisis` stops it. A queue that silenced the bot
every time someone was angry would replace a bad reply with no reply, and customers notice the
second one more.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat import attention
from app.chat.policy_guard import PolicyVerdict
from app.models import Agent, Conversation, Organization, User


async def _conv(db_session: AsyncSession) -> Conversation:
    org = Organization(name="Attn Org", slug=f"attn-{uuid.uuid4().hex[:8]}")
    db_session.add(org)
    await db_session.flush()
    agent = Agent(
        organization_id=org.id,
        name="Attn Bot",
        slug=f"attn-bot-{uuid.uuid4().hex[:6]}",
        status="draft",
        public_key=f"pk_{uuid.uuid4().hex}",
    )
    db_session.add(agent)
    await db_session.flush()
    conv = Conversation(organization_id=org.id, agent_id=agent.id, channel="widget", status="active")
    db_session.add(conv)
    await db_session.flush()
    return conv


async def test_raising_a_flag_sets_the_level_and_leaves_status_alone(db_session: AsyncSession) -> None:
    """The core of ADR-057: attention is a separate axis from the lifecycle."""
    conv = await _conv(db_session)
    await attention.raise_flag(
        db_session, conv, kind="distress", severity="elevated", signals=["rent is due"]
    )
    assert conv.attention_level == "elevated"
    assert conv.status == "active", "the bot must keep answering on elevated"


async def test_none_severity_raises_nothing(db_session: AsyncSession) -> None:
    conv = await _conv(db_session)
    assert await attention.raise_flag(db_session, conv, kind="distress", severity="none") is None
    assert conv.attention_level is None


async def test_flags_are_idempotent_per_kind_and_severity(db_session: AsyncSession) -> None:
    """Otherwise one angry conversation buries the queue in duplicates of itself."""
    conv = await _conv(db_session)
    first = await attention.raise_flag(db_session, conv, kind="distress", severity="elevated")
    second = await attention.raise_flag(db_session, conv, kind="distress", severity="elevated")
    assert first is not None and second is not None and first.id == second.id


async def test_severity_ratchets_up_and_never_down(db_session: AsyncSession) -> None:
    conv = await _conv(db_session)
    await attention.raise_flag(db_session, conv, kind="distress", severity="crisis")
    await attention.raise_flag(db_session, conv, kind="distress", severity="mild")
    assert conv.attention_level == "crisis", "calming down does not un-flag a crisis"


async def test_resolving_is_the_only_way_down(db_session: AsyncSession) -> None:
    conv = await _conv(db_session)
    # A real user: `resolved_by` is a foreign key, so the audit trail cannot point at nobody.
    user = User(email=f"resolver-{uuid.uuid4().hex[:8]}@example.com", password_hash="x")
    db_session.add(user)
    await db_session.flush()
    await attention.raise_flag(db_session, conv, kind="distress", severity="crisis")
    cleared = await attention.resolve_flags(db_session, conv, user_id=user.id)
    assert cleared == 1
    assert conv.attention_level is None


async def test_abuse_flags_even_when_distress_is_none(db_session: AsyncSession) -> None:
    conv = await _conv(db_session)
    await attention.apply_policy_verdict(
        db_session, conv, PolicyVerdict(distress="none", abuse=True, abuse_category="harassment")
    )
    assert conv.attention_level == "elevated"


async def test_applying_a_none_verdict_is_a_no_op(db_session: AsyncSession) -> None:
    conv = await _conv(db_session)
    await attention.apply_policy_verdict(db_session, conv, PolicyVerdict(distress="none"))
    assert conv.attention_level is None


# ── The queue endpoint ───────────────────────────────────────────────────────────────────


async def _headers(client: AsyncClient, email: str) -> dict[str, str]:
    signup = await client.post("/v1/auth/signup", json={"email": email, "password": "password123"})
    token = signup.json()["access_token"]
    org = await client.post("/v1/orgs", json={"name": "AttnApi"}, headers={"Authorization": f"Bearer {token}"})
    return {"Authorization": f"Bearer {token}", "X-Org-Id": org.json()["id"]}


async def test_queue_is_empty_and_does_not_error_when_nothing_is_flagged(client: AsyncClient) -> None:
    headers = await _headers(client, "attn.empty@example.com")
    r = await client.get("/v1/inbox/attention", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json() == []


async def test_queue_returns_flagged_conversations_crisis_first(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    headers = await _headers(client, "attn.order@example.com")
    org_id = uuid.UUID(headers["X-Org-Id"])
    agent = await client.post("/v1/agents", json={"name": "A"}, headers=headers)
    agent_id = uuid.UUID(agent.json()["id"])

    levels = ["mild", "crisis", "elevated"]
    for level in levels:
        conv = Conversation(organization_id=org_id, agent_id=agent_id, channel="widget", status="active")
        db_session.add(conv)
        await db_session.flush()
        await attention.raise_flag(db_session, conv, kind="distress", severity=level, signals=[level])
    await db_session.flush()

    r = await client.get("/v1/inbox/attention", headers=headers)
    assert r.status_code == 200, r.text
    got = [row["attention_level"] for row in r.json()]
    assert got == ["crisis", "elevated", "mild"], f"crisis must pin to the top, got {got}"


async def test_queue_row_carries_signals_and_says_who_is_talking(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    headers = await _headers(client, "attn.row@example.com")
    org_id = uuid.UUID(headers["X-Org-Id"])
    agent = await client.post("/v1/agents", json={"name": "A"}, headers=headers)
    conv = Conversation(
        organization_id=org_id,
        agent_id=uuid.UUID(agent.json()["id"]),
        channel="widget",
        status="active",
    )
    db_session.add(conv)
    await db_session.flush()
    await attention.raise_flag(
        db_session, conv, kind="distress", severity="elevated", signals=["rent is due"]
    )
    await db_session.flush()

    row = (await client.get("/v1/inbox/attention", headers=headers)).json()[0]
    assert row["flags"][0]["signals"] == ["rent is due"]
    assert row["flags"][0]["kind"] == "distress"
    # The bot has not been paused, and the UI must be able to say so unambiguously.
    assert row["bot_still_answering"] is True
    assert row["status"] == "active"


async def test_resolving_removes_it_from_the_queue(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    headers = await _headers(client, "attn.resolve@example.com")
    org_id = uuid.UUID(headers["X-Org-Id"])
    agent = await client.post("/v1/agents", json={"name": "A"}, headers=headers)
    conv = Conversation(
        organization_id=org_id,
        agent_id=uuid.UUID(agent.json()["id"]),
        channel="widget",
        status="active",
    )
    db_session.add(conv)
    await db_session.flush()
    await attention.raise_flag(db_session, conv, kind="distress", severity="crisis")
    await db_session.flush()

    assert len((await client.get("/v1/inbox/attention", headers=headers)).json()) == 1
    r = await client.post(f"/v1/inbox/conversations/{conv.id}/attention/resolve", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["attention_level"] is None
    assert (await client.get("/v1/inbox/attention", headers=headers)).json() == []


async def test_attention_queue_requires_inbox_permission(client: AsyncClient) -> None:
    """A viewer has no `inbox:handle`, and this queue carries distressed customers' words."""
    owner = await _headers(client, "attn.owner@example.com")
    viewer = await _headers(client, "attn.viewer@example.com")
    invite = await client.post(
        f"/v1/orgs/{owner['X-Org-Id']}/invitations",
        json={"email": "attn.viewer@example.com", "role": "viewer"},
        headers=owner,
    )
    await client.post(
        f"/v1/orgs/invitations/{invite.json()['accept_token']}/accept",
        headers={"Authorization": viewer["Authorization"]},
    )
    r = await client.get(
        "/v1/inbox/attention",
        headers={"Authorization": viewer["Authorization"], "X-Org-Id": owner["X-Org-Id"]},
    )
    assert r.status_code == 403
