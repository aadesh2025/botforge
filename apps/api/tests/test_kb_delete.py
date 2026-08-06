"""Deleting a knowledge base, and knowing what it costs before you do.

`DELETE /v1/knowledge/{id}` shipped in Phase 7 with nothing in the UI calling it, so a KB could
be created and never removed. Wiring it up made the quiet part matter: retrieval filters
`deleted_at`, so an agent still pointing at a deleted KB keeps answering — with no context
block, which is the state that makes a model invent specifics (CLAUDE.md 2026-08-02).
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings


@pytest.fixture(autouse=True)
def _no_broker(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.modules.knowledge import service

    monkeypatch.setattr(service, "enqueue_document_ingestion", lambda *_a, **_k: None)
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))


async def _headers(client: AsyncClient, email: str = "kbdel@example.com") -> dict[str, str]:
    signup = await client.post("/v1/auth/signup", json={"email": email, "password": "password123"})
    token = signup.json()["access_token"]
    org = await client.post("/v1/orgs", json={"name": "KBOrg"}, headers={"Authorization": f"Bearer {token}"})
    return {"Authorization": f"Bearer {token}", "X-Org-Id": org.json()["id"]}


async def _kb(client: AsyncClient, headers: dict[str, str], name: str = "Docs") -> dict:
    r = await client.post("/v1/knowledge", json={"name": name}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


async def _agent_using(
    client: AsyncClient, headers: dict[str, str], kb_id: str, *, name: str, publish: bool
) -> dict:
    agent = (await client.post("/v1/agents", json={"name": name}, headers=headers)).json()
    patched = await client.patch(
        f"/v1/agents/{agent['id']}/versions/1",
        json={"rag_config": {"enabled": True, "knowledge_base_ids": [kb_id]}},
        headers=headers,
    )
    assert patched.status_code == 200, patched.text
    if publish:
        pub = await client.post(f"/v1/agents/{agent['id']}/versions/1/publish", headers=headers)
        assert pub.status_code == 200, pub.text
    return agent


async def test_a_knowledge_base_can_be_deleted(client: AsyncClient) -> None:
    headers = await _headers(client)
    kb = await _kb(client, headers)

    resp = await client.delete(f"/v1/knowledge/{kb['id']}", headers=headers)
    assert resp.status_code == 204

    assert (await client.get("/v1/knowledge", headers=headers)).json() == []
    assert (await client.get(f"/v1/knowledge/{kb['id']}", headers=headers)).status_code == 404


async def test_detail_names_the_agents_that_would_lose_their_grounding(client: AsyncClient) -> None:
    headers = await _headers(client)
    kb = await _kb(client, headers)
    await _agent_using(client, headers, kb["id"], name="Live Bot", publish=True)
    await _agent_using(client, headers, kb["id"], name="Draft Bot", publish=False)

    detail = (await client.get(f"/v1/knowledge/{kb['id']}", headers=headers)).json()
    by_name = {a["name"]: a["is_live"] for a in detail["attached_agents"]}
    assert by_name == {"Draft Bot": False, "Live Bot": True}


async def test_an_agent_that_does_not_use_it_is_not_listed(client: AsyncClient) -> None:
    """The warning is only useful if it's specific — listing every agent would train people to
    click through it."""
    headers = await _headers(client)
    kb = await _kb(client, headers)
    other = await _kb(client, headers, name="Unrelated")
    await _agent_using(client, headers, other["id"], name="Elsewhere", publish=True)
    await client.post("/v1/agents", json={"name": "No RAG"}, headers=headers)

    detail = (await client.get(f"/v1/knowledge/{kb['id']}", headers=headers)).json()
    assert detail["attached_agents"] == []


async def test_the_list_does_not_pay_for_usage_lookups(client: AsyncClient) -> None:
    headers = await _headers(client)
    kb = await _kb(client, headers)
    await _agent_using(client, headers, kb["id"], name="Live Bot", publish=True)

    listed = (await client.get("/v1/knowledge", headers=headers)).json()
    assert listed[0]["attached_agents"] == [], "the list is one query per card without this"


async def test_deleting_leaves_the_attached_agent_answering_without_context(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Pinning the behaviour the confirmation dialog warns about: the agent is not broken, it
    just silently has nothing to retrieve from."""
    import uuid as _uuid

    from sqlalchemy import select

    from app.models import Agent, AgentVersion
    from app.rag.agent_retrieval import retrieve_for_version

    headers = await _headers(client)
    kb = await _kb(client, headers)
    agent = await _agent_using(client, headers, kb["id"], name="Live Bot", publish=True)

    version = (
        await db_session.execute(
            select(AgentVersion).where(AgentVersion.agent_id == _uuid.UUID(agent["id"]))
        )
    ).scalars().first()
    assert version is not None
    org_id = _uuid.UUID(headers["X-Org-Id"])

    # Grounded while the KB exists (no documents, so no citations — but the KB resolves).
    before, _ = await retrieve_for_version(db_session, org_id, version, "anything")

    await client.delete(f"/v1/knowledge/{kb['id']}", headers=headers)
    after, citations = await retrieve_for_version(db_session, org_id, version, "anything")

    assert after == "" and citations == []
    assert version.rag_config["knowledge_base_ids"] == [kb["id"]], (
        "the reference is deliberately left in place — the agent's config is not rewritten "
        "behind the operator's back, which is why the dialog tells them to detach it"
    )
    assert before == after == ""


async def test_deleting_requires_kb_manage(client: AsyncClient) -> None:
    headers = await _headers(client)
    kb = await _kb(client, headers)

    # A viewer invited into the same org may read the KB but not remove it.
    inv = await client.post(
        f"/v1/orgs/{headers['X-Org-Id']}/invitations",
        json={"email": "viewer@example.com", "role": "viewer"},
        headers=headers,
    )
    token = inv.json()["accept_token"]
    viewer = (
        await client.post("/v1/auth/signup", json={"email": "viewer@example.com", "password": "password123"})
    ).json()["access_token"]
    await client.post(
        f"/v1/orgs/invitations/{token}/accept", headers={"Authorization": f"Bearer {viewer}"}
    )
    vh = {"Authorization": f"Bearer {viewer}", "X-Org-Id": headers["X-Org-Id"]}

    assert (await client.get(f"/v1/knowledge/{kb['id']}", headers=vh)).status_code == 200
    assert (await client.delete(f"/v1/knowledge/{kb['id']}", headers=vh)).status_code == 403
