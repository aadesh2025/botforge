"""Phase 6: agents, versions, and the playground (real DB, tx-rollback)."""

from __future__ import annotations

import re

import pytest
from httpx import AsyncClient

from app.core.email import get_email_backend
from app.llm.fake import FakeChatProvider


async def _headers(client: AsyncClient, email: str = "a@example.com") -> tuple[dict[str, str], dict]:
    signup = await client.post("/v1/auth/signup", json={"email": email, "password": "password123"})
    token = signup.json()["access_token"]
    org = await client.post("/v1/orgs", json={"name": "Acme"}, headers={"Authorization": f"Bearer {token}"})
    org_json = org.json()
    return {"Authorization": f"Bearer {token}", "X-Org-Id": org_json["id"]}, org_json


async def _create_agent(client: AsyncClient, headers: dict[str, str], name: str = "Bot") -> dict:
    r = await client.post("/v1/agents", json={"name": name, "description": "d"}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


# ── CRUD ──────────────────────────────────────────────────────────────────────
async def test_create_list_get_agent(client: AsyncClient) -> None:
    headers, _ = await _headers(client)
    agent = await _create_agent(client, headers)
    assert agent["status"] == "draft"
    assert agent["public_key"].startswith("bf_pub_")
    assert agent["draft_version"] == 1
    assert agent["current_version_id"] is None

    listed = await client.get("/v1/agents", headers=headers)
    assert [a["id"] for a in listed.json()] == [agent["id"]]

    got = await client.get(f"/v1/agents/{agent['id']}", headers=headers)
    assert got.status_code == 200


async def test_update_and_delete_agent(client: AsyncClient) -> None:
    headers, _ = await _headers(client)
    agent = await _create_agent(client, headers)
    patched = await client.patch(
        f"/v1/agents/{agent['id']}", json={"name": "Renamed"}, headers=headers
    )
    assert patched.json()["name"] == "Renamed"

    assert (await client.delete(f"/v1/agents/{agent['id']}", headers=headers)).status_code == 204
    assert (await client.get(f"/v1/agents/{agent['id']}", headers=headers)).status_code == 404


async def test_duplicate_agent(client: AsyncClient) -> None:
    headers, _ = await _headers(client)
    agent = await _create_agent(client, headers, "Original")
    dup = await client.post(f"/v1/agents/{agent['id']}/duplicate", headers=headers)
    assert dup.status_code == 201
    assert dup.json()["name"] == "Original (copy)"
    assert dup.json()["id"] != agent["id"]


# ── Versions ──────────────────────────────────────────────────────────────────
async def test_version_lifecycle(client: AsyncClient) -> None:
    headers, _ = await _headers(client)
    agent = await _create_agent(client, headers)
    aid = agent["id"]

    # Patch draft v1 (note: JSON key is model_config, aliased server-side).
    patch = await client.patch(
        f"/v1/agents/{aid}/versions/1",
        json={
            "system_prompt": "You are helpful.",
            "welcome_message": "Hey!",
            "model_config": {"provider": "groq", "model": "llama-3.1-8b-instant", "temperature": 0.2},
        },
        headers=headers,
    )
    assert patch.status_code == 200
    assert patch.json()["system_prompt"] == "You are helpful."
    assert patch.json()["model_config"]["model"] == "llama-3.1-8b-instant"

    # Publish v1.
    published = await client.post(f"/v1/agents/{aid}/versions/1/publish", headers=headers)
    assert published.status_code == 200
    assert published.json()["status"] == "published"
    v1_current = published.json()["current_version_id"]
    assert v1_current is not None

    # New draft v2 copies from v1, edit + publish → current moves to v2.
    v2 = await client.post(f"/v1/agents/{aid}/versions", headers=headers)
    assert v2.json()["version"] == 2
    assert v2.json()["system_prompt"] == "You are helpful."  # copied
    await client.post(f"/v1/agents/{aid}/versions/2/publish", headers=headers)

    agent_now = (await client.get(f"/v1/agents/{aid}", headers=headers)).json()
    assert agent_now["current_version_id"] != v1_current

    # Roll back to v1.
    rolled = await client.post(f"/v1/agents/{aid}/rollback", json={"version": 1}, headers=headers)
    assert rolled.json()["current_version_id"] == v1_current

    versions = await client.get(f"/v1/agents/{aid}/versions", headers=headers)
    assert {v["version"] for v in versions.json()} == {1, 2}


async def test_branch_on_edit_forks_draft_from_published(client: AsyncClient) -> None:
    """Editing a published version transparently forks a new draft (no silent 409)."""
    headers, _ = await _headers(client)
    agent = await _create_agent(client, headers)
    aid = agent["id"]

    await client.patch(f"/v1/agents/{aid}/versions/1", json={"system_prompt": "original"}, headers=headers)
    await client.post(f"/v1/agents/{aid}/versions/1/publish", headers=headers)

    # Patching the now-published v1 forks v2 and applies the change there.
    resp = await client.patch(
        f"/v1/agents/{aid}/versions/1", json={"system_prompt": "edited after publish"}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["version"] == 2
    assert body["is_published"] is False
    assert body["system_prompt"] == "edited after publish"

    # v1 remains published and unchanged.
    versions = {v["version"]: v for v in (await client.get(f"/v1/agents/{aid}/versions", headers=headers)).json()}
    assert versions[1]["is_published"] is True
    assert versions[1]["system_prompt"] == "original"
    assert set(versions) == {1, 2}


# ── RBAC ──────────────────────────────────────────────────────────────────────
async def test_viewer_cannot_create_agent(client: AsyncClient) -> None:
    owner_headers, org = await _headers(client, "owner@example.com")
    invite = await client.post(
        f"/v1/orgs/{org['id']}/invitations", json={"email": "v@example.com", "role": "viewer"},
        headers=owner_headers,
    )
    assert invite.status_code == 201
    token = re.search(r"Token:\s*(\S+)", get_email_backend().outbox[-1].body).group(1)  # type: ignore[union-attr]
    signup = await client.post("/v1/auth/signup", json={"email": "v@example.com", "password": "password123"})
    viewer_token = signup.json()["access_token"]
    await client.post(f"/v1/orgs/invitations/{token}/accept", headers={"Authorization": f"Bearer {viewer_token}"})

    viewer_headers = {"Authorization": f"Bearer {viewer_token}", "X-Org-Id": org["id"]}
    r = await client.post("/v1/agents", json={"name": "Nope"}, headers=viewer_headers)
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "org.forbidden"


# ── Playground ────────────────────────────────────────────────────────────────
async def test_playground_streams(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.modules.agents import service

    async def _fake_provider(*_a: object, **_k: object) -> FakeChatProvider:
        return FakeChatProvider()

    monkeypatch.setattr(service, "get_chat_provider", _fake_provider)

    headers, _ = await _headers(client)
    agent = await _create_agent(client, headers)

    resp = await client.post(
        f"/v1/agents/{agent['id']}/playground/chat",
        json={"message": "hello there", "stream": True},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.text
    assert '"type":"token"' in body
    assert '"type":"done"' in body


async def test_playground_non_stream(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.modules.agents import service

    async def _fake_provider(*_a: object, **_k: object) -> FakeChatProvider:
        return FakeChatProvider()

    monkeypatch.setattr(service, "get_chat_provider", _fake_provider)

    headers, _ = await _headers(client)
    agent = await _create_agent(client, headers)
    resp = await client.post(
        f"/v1/agents/{agent['id']}/playground/chat",
        json={"message": "hi", "stream": False},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["content"] == "echo: hi"


# ── Playground turns are real, reportable traffic ─────────────────────────────
# The Playground used to persist nothing, so an operator testing an agent all afternoon saw
# a dashboard that never moved — the single most common "my analytics are fake" report.
async def test_playground_persists_the_turn_under_its_own_channel(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.modules.agents import service

    async def _fake_provider(*_a: object, **_k: object) -> FakeChatProvider:
        return FakeChatProvider()

    monkeypatch.setattr(service, "get_chat_provider", _fake_provider)

    headers, _ = await _headers(client)
    agent = await _create_agent(client, headers)
    resp = await client.post(
        f"/v1/agents/{agent['id']}/playground/chat",
        json={"message": "hi", "stream": False},
        headers=headers,
    )
    assert resp.status_code == 200
    cid = resp.json()["conversation_id"]

    convs = await client.get("/v1/conversations", headers=headers)
    assert convs.status_code == 200
    mine = [c for c in convs.json() if c["id"] == cid]
    assert len(mine) == 1, "the playground turn did not create a conversation"
    assert mine[0]["channel"] == "playground", "must be distinguishable from customer traffic"

    detail = await client.get(f"/v1/conversations/{cid}", headers=headers)
    roles = [m["role"] for m in detail.json()["messages"]]
    assert roles == ["user", "assistant"], "both halves of the turn must be recorded"


async def test_playground_threads_turns_onto_one_conversation(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without a threaded id every turn would open its own conversation, so a ten-message
    test session would report as ten conversations and wreck the headline number."""
    from app.modules.agents import service

    async def _fake_provider(*_a: object, **_k: object) -> FakeChatProvider:
        return FakeChatProvider()

    monkeypatch.setattr(service, "get_chat_provider", _fake_provider)

    headers, _ = await _headers(client)
    agent = await _create_agent(client, headers)

    first = await client.post(
        f"/v1/agents/{agent['id']}/playground/chat",
        json={"message": "one", "stream": False},
        headers=headers,
    )
    cid = first.json()["conversation_id"]
    second = await client.post(
        f"/v1/agents/{agent['id']}/playground/chat",
        json={"message": "two", "stream": False, "conversation_id": cid},
        headers=headers,
    )
    assert second.json()["conversation_id"] == cid

    detail = await client.get(f"/v1/conversations/{cid}", headers=headers)
    assert len(detail.json()["messages"]) == 4


async def test_playground_stream_announces_its_conversation_first(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The id is emitted ahead of the first token so a stream the operator navigates away
    from still leaves the client able to thread the next turn."""
    from app.modules.agents import service

    async def _fake_provider(*_a: object, **_k: object) -> FakeChatProvider:
        return FakeChatProvider()

    monkeypatch.setattr(service, "get_chat_provider", _fake_provider)

    headers, _ = await _headers(client)
    agent = await _create_agent(client, headers)
    resp = await client.post(
        f"/v1/agents/{agent['id']}/playground/chat",
        json={"message": "hello", "stream": True},
        headers=headers,
    )
    body = resp.text
    assert '"type": "conversation"' in body
    assert body.index("conversation_id") < body.index('"type":"token"')


# ── Creation-time role templates ──────────────────────────────────────────────
async def test_list_agent_templates(client: AsyncClient) -> None:
    headers, _ = await _headers(client)
    resp = await client.get("/v1/agent-templates", headers=headers)
    assert resp.status_code == 200
    templates = resp.json()
    assert {t["id"] for t in templates} == {
        "customer_support",
        "lead_qualification",
        "appointment_scheduler",
        "info_collector",
    }
    for t in templates:
        assert t["label"] and t["icon"] and t["description"]
        assert t["system_prompt"] and t["welcome_message"] and t["tone"]
        assert isinstance(t["suggested_prompts"], list)


async def test_agent_templates_require_auth(client: AsyncClient) -> None:
    assert (await client.get("/v1/agent-templates")).status_code == 401


async def test_create_agent_from_template_seeds_draft(client: AsyncClient) -> None:
    headers, _ = await _headers(client)
    catalog = {t["id"]: t for t in (await client.get("/v1/agent-templates", headers=headers)).json()}

    for template_id, template in catalog.items():
        created = await client.post(
            "/v1/agents",
            json={"name": f"Bot {template_id}", "template_id": template_id},
            headers=headers,
        )
        assert created.status_code == 201, created.text
        versions = await client.get(f"/v1/agents/{created.json()['id']}/versions", headers=headers)
        draft = versions.json()[0]

        assert draft["version"] == 1 and draft["is_published"] is False
        assert draft["system_prompt"] == template["system_prompt"]
        assert draft["welcome_message"] == template["welcome_message"]
        assert draft["suggested_prompts"] == template["suggested_prompts"]
        # The template id is recorded so the builder can show its next-step hint.
        assert draft["persona"] == {"tone": template["tone"], "template_id": template_id}
        # model_overrides are merged over the defaults, never replacing them wholesale.
        assert draft["model_config"]["provider"] == "groq"
        assert draft["model_config"]["max_tokens"] == 1024


async def test_scheduler_template_lowers_temperature(client: AsyncClient) -> None:
    """A template may override model settings; the rest of DEFAULT_MODEL_CONFIG survives."""
    headers, _ = await _headers(client)
    created = await client.post(
        "/v1/agents",
        json={"name": "Scheduler", "template_id": "appointment_scheduler"},
        headers=headers,
    )
    versions = await client.get(f"/v1/agents/{created.json()['id']}/versions", headers=headers)
    assert versions.json()[0]["model_config"]["temperature"] == 0.2


async def test_create_agent_without_template_is_unchanged(client: AsyncClient) -> None:
    """The blank path must keep working — nobody is forced through the picker."""
    from app.modules.agents.service import DEFAULT_MODEL_CONFIG, DEFAULT_SYSTEM_PROMPT

    headers, _ = await _headers(client)
    agent = await _create_agent(client, headers)
    draft = (await client.get(f"/v1/agents/{agent['id']}/versions", headers=headers)).json()[0]

    assert draft["system_prompt"] == DEFAULT_SYSTEM_PROMPT
    assert draft["welcome_message"] == "Hi! How can I help you today?"
    assert draft["suggested_prompts"] == []
    assert draft["persona"] == {}
    assert draft["model_config"] == DEFAULT_MODEL_CONFIG


async def test_create_agent_with_unknown_template_is_rejected(client: AsyncClient) -> None:
    """A typo must not silently produce a blank agent, and must not create one either."""
    headers, _ = await _headers(client)
    resp = await client.post(
        "/v1/agents", json={"name": "Nope", "template_id": "not_a_template"}, headers=headers
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "agents.unknown_template"
    assert (await client.get("/v1/agents", headers=headers)).json() == []


async def test_template_prompts_never_ask_for_citation_markers(client: AsyncClient) -> None:
    """Part 1's rule has to hold for the seeded prompts too, not just the RAG header."""
    headers, _ = await _headers(client)
    for t in (await client.get("/v1/agent-templates", headers=headers)).json():
        prompt = t["system_prompt"].lower()
        assert "cite" not in prompt, f"{t['id']} asks the model to cite sources"
        # The phrase appears only inside the explicit prohibition.
        assert "never narrate your sources" in prompt
        assert "according to the documents" in prompt.split("never narrate your sources")[1]


async def test_every_seeded_prompt_still_refuses_to_guess(client: AsyncClient) -> None:
    """Softening the *voice* must never soften the grounding.

    This pins a regression that a unit test alone could not have caught, so it pins the prompt
    text instead. Rewriting `DEFAULT_SYSTEM_PROMPT` for tone once ended the never-narrate-your-
    sources rule with "Just answer." — and with no retrieved context the model read that as
    "don't hedge" and invented support hours and a refund window in 3 of 3 sampled replies,
    where the previous prompt refused in 3 of 3. The two clauses asserted below are what closed
    it: the prohibition is scoped to phrasing, and the no-context case is stated outright.
    """
    from app.modules.agents.service import DEFAULT_SYSTEM_PROMPT

    headers, _ = await _headers(client)
    templates = (await client.get("/v1/agent-templates", headers=headers)).json()
    prompts = [("default", DEFAULT_SYSTEM_PROMPT)] + [(t["id"], t["system_prompt"]) for t in templates]

    for name, raw in prompts:
        prompt = raw.lower()
        assert "only" in prompt and "context" in prompt, f"{name} dropped the only-from-context rule"
        assert "do not guess" in prompt or "do not use" in prompt, f"{name} dropped the no-guess rule"
        # The no-context case has to be spelled out; "there is no context" is the exact state the
        # model over-answered in.
        assert "no context was provided" in prompt, f"{name} leaves the no-retrieval case implicit"
        # The prohibition must be scoped, or it reads as licence to answer anyway.
        assert "phrasing only" in prompt, f"{name} lets 'don't cite sources' imply 'answer anyway'"
        assert "just answer." not in prompt, f"{name} reintroduced the phrase that caused the regression"
