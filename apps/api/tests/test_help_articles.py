"""Help Center: authoring, public reads, and the opt-in push into the agent's RAG store."""

from __future__ import annotations

from httpx import AsyncClient


async def _headers(client: AsyncClient, email: str, org: str = "HelpOrg") -> dict[str, str]:
    signup = await client.post("/v1/auth/signup", json={"email": email, "password": "password123"})
    token = signup.json()["access_token"]
    o = await client.post("/v1/orgs", json={"name": org}, headers={"Authorization": f"Bearer {token}"})
    return {"Authorization": f"Bearer {token}", "X-Org-Id": o.json()["id"]}


async def _agent(client: AsyncClient, headers: dict[str, str]) -> tuple[str, str]:
    agent = await client.post("/v1/agents", json={"name": "Help Bot"}, headers=headers)
    return str(agent.json()["id"]), str(agent.json()["public_key"])


async def _agent_with_kb(client: AsyncClient, headers: dict[str, str]) -> tuple[str, str, str]:
    aid, key = await _agent(client, headers)
    kb = await client.post(
        "/v1/knowledge", json={"name": "Docs"}, headers=headers
    )
    assert kb.status_code in (200, 201), kb.text
    kb_id = kb.json()["id"]
    await client.patch(
        f"/v1/agents/{aid}/versions/1",
        json={"rag_config": {"enabled": True, "knowledge_base_ids": [kb_id]}},
        headers=headers,
    )
    return aid, key, kb_id


async def test_crud_and_slug_generation(client: AsyncClient) -> None:
    headers = await _headers(client, "help1@example.com")
    aid, _key = await _agent(client, headers)

    created = await client.post(
        "/v1/help-articles",
        json={"agent_id": aid, "title": "How do refunds work?", "body_markdown": "# Refunds\n\nWithin 30 days."},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    # Slug derived from the title when the author doesn't supply one.
    assert created.json()["slug"] == "how-do-refunds-work"
    assert created.json()["published"] is False

    article_id = created.json()["id"]
    updated = await client.patch(
        f"/v1/help-articles/{article_id}", json={"category": "Billing", "published": True}, headers=headers
    )
    assert updated.json()["category"] == "Billing" and updated.json()["published"] is True

    assert (await client.get("/v1/help-articles", headers=headers)).json()[0]["id"] == article_id
    assert (await client.delete(f"/v1/help-articles/{article_id}", headers=headers)).status_code == 204


async def test_duplicate_slug_per_agent_rejected(client: AsyncClient) -> None:
    """Slugs address articles in public URLs, so they must be unique per agent."""
    headers = await _headers(client, "help2@example.com")
    aid, _key = await _agent(client, headers)
    body = {"agent_id": aid, "title": "Getting started", "body_markdown": "x"}
    assert (await client.post("/v1/help-articles", json=body, headers=headers)).status_code == 201
    dup = await client.post("/v1/help-articles", json=body, headers=headers)
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "help.duplicate_slug"


async def test_public_endpoints_show_only_published(client: AsyncClient) -> None:
    headers = await _headers(client, "help3@example.com")
    aid, key = await _agent(client, headers)
    await client.post(
        "/v1/help-articles",
        json={"agent_id": aid, "title": "Live one", "body_markdown": "visible", "published": True},
        headers=headers,
    )
    await client.post(
        "/v1/help-articles",
        json={"agent_id": aid, "title": "Draft one", "body_markdown": "secret", "published": False},
        headers=headers,
    )

    # No auth header at all — these are public pages.
    listed = await client.get(f"/v1/public/agents/{key}/help")
    assert listed.status_code == 200, listed.text
    assert [a["title"] for a in listed.json()] == ["Live one"]

    article = await client.get(f"/v1/public/agents/{key}/help/live-one")
    assert article.status_code == 200
    assert article.json()["body_markdown"] == "visible"

    # A draft is indistinguishable from a missing article from outside.
    assert (await client.get(f"/v1/public/agents/{key}/help/draft-one")).status_code == 404


async def test_publish_with_sync_pushes_into_the_agents_knowledge_base(client: AsyncClient) -> None:
    headers = await _headers(client, "help4@example.com")
    aid, _key, kb_id = await _agent_with_kb(client, headers)

    created = await client.post(
        "/v1/help-articles",
        json={
            "agent_id": aid,
            "title": "Shipping times",
            "body_markdown": "Orders ship in 2 days.",
            "published": True,
            "sync_to_kb": True,
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    doc_id = created.json()["kb_document_id"]
    assert doc_id, "publishing with sync should create a RAG document"

    docs = await client.get(f"/v1/knowledge/{kb_id}/documents", headers=headers)
    assert any(d["id"] == doc_id for d in docs.json())

    # Editing the body replaces the document rather than accumulating a stale copy.
    edited = await client.patch(
        f"/v1/help-articles/{created.json()['id']}",
        json={"body_markdown": "Orders ship in 1 day."},
        headers=headers,
    )
    new_doc_id = edited.json()["kb_document_id"]
    assert new_doc_id and new_doc_id != doc_id
    docs = await client.get(f"/v1/knowledge/{kb_id}/documents", headers=headers)
    ids = [d["id"] for d in docs.json()]
    assert doc_id not in ids and new_doc_id in ids


async def test_unpublishing_removes_it_from_the_knowledge_base(client: AsyncClient) -> None:
    """The AI shouldn't keep answering from an article a human can no longer read."""
    headers = await _headers(client, "help5@example.com")
    aid, _key, kb_id = await _agent_with_kb(client, headers)
    created = await client.post(
        "/v1/help-articles",
        json={
            "agent_id": aid,
            "title": "Temporary notice",
            "body_markdown": "Closed for the holidays.",
            "published": True,
            "sync_to_kb": True,
        },
        headers=headers,
    )
    doc_id = created.json()["kb_document_id"]

    unpublished = await client.patch(
        f"/v1/help-articles/{created.json()['id']}", json={"published": False}, headers=headers
    )
    assert unpublished.json()["kb_document_id"] is None
    docs = await client.get(f"/v1/knowledge/{kb_id}/documents", headers=headers)
    assert doc_id not in [d["id"] for d in docs.json()]


async def test_sync_without_a_knowledge_base_says_so(client: AsyncClient) -> None:
    """Writing into a KB the agent doesn't read would look like it worked and change nothing."""
    headers = await _headers(client, "help6@example.com")
    aid, _key = await _agent(client, headers)
    r = await client.post(
        "/v1/help-articles",
        json={
            "agent_id": aid,
            "title": "Orphan",
            "body_markdown": "x",
            "published": True,
            "sync_to_kb": True,
        },
        headers=headers,
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "help.no_knowledge_base"


async def test_tenant_isolation(client: AsyncClient) -> None:
    a = await _headers(client, "help-a@example.com", org="OrgA")
    b = await _headers(client, "help-b@example.com", org="OrgB")
    aid, _key = await _agent(client, a)
    created = await client.post(
        "/v1/help-articles", json={"agent_id": aid, "title": "Theirs", "body_markdown": "x"}, headers=a
    )
    assert (await client.get("/v1/help-articles", headers=b)).json() == []
    cross = await client.patch(
        f"/v1/help-articles/{created.json()['id']}", json={"title": "Mine"}, headers=b
    )
    assert cross.status_code == 404
