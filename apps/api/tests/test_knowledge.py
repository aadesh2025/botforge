"""Phase 7 tests: KB CRUD, document ingestion, retrieval, and RAG-in-playground.

DB-backed and run against real Postgres inside the tx-rollback session. Ingestion is exercised
by calling the pipeline directly (the Celery enqueue is stubbed so nothing hits the broker).
"""

from __future__ import annotations

import re
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.email import get_email_backend
from app.llm.fake import FakeChatProvider
from app.rag.ingest import ingest_document


@pytest.fixture(autouse=True)
def _no_broker_and_tmp_uploads(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.modules.knowledge import service

    # Ingestion is invoked directly in tests; don't push to the real Celery broker.
    monkeypatch.setattr(service, "enqueue_document_ingestion", lambda *_a, **_k: None)
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))


async def _headers(client: AsyncClient, email: str = "kb@example.com") -> dict[str, str]:
    signup = await client.post("/v1/auth/signup", json={"email": email, "password": "password123"})
    token = signup.json()["access_token"]
    org = await client.post("/v1/orgs", json={"name": "KBOrg"}, headers={"Authorization": f"Bearer {token}"})
    return {"Authorization": f"Bearer {token}", "X-Org-Id": org.json()["id"]}


async def _create_kb(client: AsyncClient, headers: dict[str, str], name: str = "Docs") -> dict:
    r = await client.post(
        "/v1/knowledge",
        json={"name": name, "embedding_provider": "fake", "embedding_model": "fake-embed"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _add_text(client: AsyncClient, headers: dict[str, str], kb_id: str, text: str) -> dict:
    r = await client.post(
        f"/v1/knowledge/{kb_id}/documents",
        json={"source_type": "text", "text": text, "filename": "note.txt"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


# ── KB CRUD ─────────────────────────────────────────────────────────────────────
async def test_kb_crud(client: AsyncClient) -> None:
    headers = await _headers(client)
    kb = await _create_kb(client, headers)
    assert kb["embedding_provider"] == "fake"
    assert kb["document_count"] == 0

    listed = await client.get("/v1/knowledge", headers=headers)
    assert [k["id"] for k in listed.json()] == [kb["id"]]

    patched = await client.patch(f"/v1/knowledge/{kb['id']}", json={"name": "Renamed"}, headers=headers)
    assert patched.json()["name"] == "Renamed"

    assert (await client.delete(f"/v1/knowledge/{kb['id']}", headers=headers)).status_code == 204
    assert (await client.get(f"/v1/knowledge/{kb['id']}", headers=headers)).status_code == 404


# ── Upload + ingestion ──────────────────────────────────────────────────────────
async def test_text_document_ingests_to_ready(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _headers(client)
    kb = await _create_kb(client, headers)
    doc = await _add_text(
        client, headers, kb["id"], "Lumina is the capital city of Zephyria. It sits by the sea."
    )
    assert doc["status"] == "queued"
    assert doc["source_type"] == "text"

    await ingest_document(db_session, uuid.UUID(doc["id"]))

    got = await client.get(f"/v1/knowledge/documents/{doc['id']}", headers=headers)
    assert got.json()["status"] == "ready"
    assert got.json()["chunk_count"] >= 1

    chunks = await client.get(f"/v1/knowledge/documents/{doc['id']}/chunks", headers=headers)
    assert len(chunks.json()) >= 1
    assert "Zephyria" in chunks.json()[0]["content"]

    kb_now = await client.get(f"/v1/knowledge/{kb['id']}", headers=headers)
    assert kb_now.json()["document_count"] == 1


async def test_file_upload_ingests(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _headers(client)
    kb = await _create_kb(client, headers)
    files = {"file": ("facts.txt", b"Orion is a constellation visible in winter.", "text/plain")}
    r = await client.post(f"/v1/knowledge/{kb['id']}/documents/upload", files=files, headers=headers)
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc["source_type"] == "file"
    assert doc["size_bytes"] > 0

    await ingest_document(db_session, uuid.UUID(doc["id"]))
    got = await client.get(f"/v1/knowledge/documents/{doc['id']}", headers=headers)
    assert got.json()["status"] == "ready"


async def test_reingest_and_delete_document(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _headers(client)
    kb = await _create_kb(client, headers)
    doc = await _add_text(client, headers, kb["id"], "Some content to index here.")
    await ingest_document(db_session, uuid.UUID(doc["id"]))

    re_r = await client.post(f"/v1/knowledge/documents/{doc['id']}/reingest", headers=headers)
    assert re_r.status_code == 200
    assert re_r.json()["status"] == "queued"

    assert (await client.delete(f"/v1/knowledge/documents/{doc['id']}", headers=headers)).status_code == 204
    assert (await client.get(f"/v1/knowledge/documents/{doc['id']}", headers=headers)).status_code == 404


# ── Retrieval ───────────────────────────────────────────────────────────────────
async def test_vector_search_exact_match(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _headers(client)
    kb = await _create_kb(client, headers)
    sentence = "Lumina is the capital city of Zephyria."
    doc = await _add_text(client, headers, kb["id"], sentence)
    await ingest_document(db_session, uuid.UUID(doc["id"]))

    # Fake embeddings are deterministic per string → an exact query matches with similarity ~1.
    r = await client.post(
        f"/v1/knowledge/{kb['id']}/search",
        json={"query": sentence, "hybrid": False, "score_threshold": 0.5, "top_k": 3},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    cites = r.json()["citations"]
    assert len(cites) == 1
    assert cites[0]["score"] > 0.99
    assert cites[0]["knowledge_base_id"] == kb["id"]


async def test_hybrid_search_finds_lexical_match(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _headers(client)
    kb = await _create_kb(client, headers)
    doc = await _add_text(
        client, headers, kb["id"], "The Zephyria capital is Lumina, a coastal metropolis of note."
    )
    await ingest_document(db_session, uuid.UUID(doc["id"]))

    r = await client.post(
        f"/v1/knowledge/{kb['id']}/search",
        json={"query": "Zephyria capital", "hybrid": True, "top_k": 5},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    cites = r.json()["citations"]
    assert cites and any("Zephyria" in c["content"] for c in cites)


# ── RBAC ────────────────────────────────────────────────────────────────────────
async def test_viewer_cannot_create_kb(client: AsyncClient) -> None:
    owner = await _headers(client, "kbowner@example.com")
    org_id = owner["X-Org-Id"]
    invite = await client.post(
        f"/v1/orgs/{org_id}/invitations", json={"email": "kv@example.com", "role": "viewer"}, headers=owner
    )
    assert invite.status_code == 201
    token = re.search(r"Token:\s*(\S+)", get_email_backend().outbox[-1].body).group(1)  # type: ignore[union-attr]
    signup = await client.post("/v1/auth/signup", json={"email": "kv@example.com", "password": "password123"})
    viewer_token = signup.json()["access_token"]
    await client.post(f"/v1/orgs/invitations/{token}/accept", headers={"Authorization": f"Bearer {viewer_token}"})

    viewer_headers = {"Authorization": f"Bearer {viewer_token}", "X-Org-Id": org_id}
    r = await client.post("/v1/knowledge", json={"name": "Nope"}, headers=viewer_headers)
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "org.forbidden"


# ── RAG wired into the playground ────────────────────────────────────────────────
async def test_playground_returns_rag_citations(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.modules.agents import service as agents_service

    async def _fake_provider(*_a: object, **_k: object) -> FakeChatProvider:
        return FakeChatProvider()

    monkeypatch.setattr(agents_service, "get_chat_provider", _fake_provider)

    headers = await _headers(client)
    kb = await _create_kb(client, headers)
    doc = await _add_text(client, headers, kb["id"], "Zephyria's capital is Lumina, home to the grand library.")
    await ingest_document(db_session, uuid.UUID(doc["id"]))

    agent = await client.post("/v1/agents", json={"name": "RAG Bot"}, headers=headers)
    aid = agent.json()["id"]
    patch = await client.patch(
        f"/v1/agents/{aid}/versions/1",
        json={
            "system_prompt": "Answer from context.",
            "rag_config": {
                "enabled": True,
                "knowledge_base_ids": [kb["id"]],
                "top_k": 3,
                "score_threshold": 0.0,
                "hybrid": True,
            },
        },
        headers=headers,
    )
    assert patch.status_code == 200

    resp = await client.post(
        f"/v1/agents/{aid}/playground/chat",
        json={"message": "Zephyria capital", "stream": True},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.text
    assert '"type":"citations"' in body
    assert "Lumina" in body
