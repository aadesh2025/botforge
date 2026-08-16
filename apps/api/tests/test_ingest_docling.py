"""Docling wired into the real ingest pipeline (docs/14 K1-3/K1-4).

`test_converters.py` covers the converter in isolation. This file covers the thing that
actually has to hold in production: **a document row reaches `status=ready` either way.**

The failure being guarded against is not subtle. If a Docling outage propagated, every upload
during it would land as `status=failed` with an error message about an internal service, and
nothing re-drives a failed document — a client would have to notice and re-upload. That is
strictly worse than extracting with `pypdf`, which is what this repo did last week.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import Chunk, Document, KnowledgeBase, Organization
from app.rag.converters import BACKEND_DOCLING, BACKEND_LEGACY
from app.rag.ingest import ingest_document

BODY = """Returns Policy

Refunds are processed within 14 days of the original purchase date.
"""

DOCLING_MD = "# Returns Policy\n\n## International Orders\n\nRefunds within 30 days of delivery."
DOCLING_JSON = {"schema_name": "DoclingDocument", "name": "policy"}


async def _document(session: AsyncSession, tmp_path, text: str = BODY) -> Document:  # type: ignore[no-untyped-def]
    org = Organization(name="Docling Org", slug=f"docling-{uuid.uuid4().hex[:8]}")
    session.add(org)
    await session.flush()
    kb = KnowledgeBase(
        organization_id=org.id, name="KB", embedding_provider="fake", embedding_model="fake-embed"
    )
    session.add(kb)
    await session.flush()
    path = tmp_path / "policy.txt"
    path.write_text(text, encoding="utf-8")
    doc = Document(
        knowledge_base_id=kb.id,
        organization_id=org.id,
        source_type="text",
        filename="policy.txt",
        mime_type="text/plain",
        status="queued",
        storage_path=str(path),
    )
    session.add(doc)
    await session.flush()
    return doc


def _enabled():  # type: ignore[no-untyped-def]
    class _Ctx:
        def __enter__(self) -> None:
            self._prev = (settings.docling_enabled, settings.docling_endpoint)
            settings.docling_enabled = True
            settings.docling_endpoint = "http://docling:5001"

        def __exit__(self, *exc: object) -> None:
            settings.docling_enabled, settings.docling_endpoint = self._prev

    return _Ctx()


def _ok() -> httpx.MockTransport:
    return httpx.MockTransport(
        lambda r: httpx.Response(
            200, json={"document": {"md_content": DOCLING_MD, "json_content": DOCLING_JSON}}
        )
    )


def _down() -> httpx.MockTransport:
    return httpx.MockTransport(lambda r: httpx.Response(503, text="unavailable"))


def _read_json(path: str) -> object:
    """Sync on purpose — reading a local file from an async test trips ruff ASYNC240, and the
    blocking read is honest here for the same reason it is in `ingest._stored_bytes`."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


async def _chunk_texts(session: AsyncSession, doc: Document) -> list[str]:
    rows = await session.execute(
        select(Chunk.content).where(Chunk.document_id == doc.id).order_by(Chunk.ordinal)
    )
    return list(rows.scalars().all())


# ── both directions, same input ──────────────────────────────────────────────────────────

async def test_docling_output_is_what_gets_chunked(db_session: AsyncSession, tmp_path) -> None:  # type: ignore[no-untyped-def]
    doc = await _document(db_session, tmp_path)
    with _enabled():
        await ingest_document(db_session, doc.id, docling_transport=_ok())
    await db_session.refresh(doc)

    assert doc.status == "ready", doc.error_message
    assert doc.extraction_backend == BACKEND_DOCLING
    assert "International Orders" in "\n".join(await _chunk_texts(db_session, doc))


async def test_a_docling_outage_still_ingests_the_document(
    db_session: AsyncSession, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    """The whole point of K1-3. Same document, service down, still `ready`."""
    doc = await _document(db_session, tmp_path)
    with _enabled():
        await ingest_document(db_session, doc.id, docling_transport=_down())
    await db_session.refresh(doc)

    assert doc.status == "ready", doc.error_message
    assert doc.error_message is None
    assert doc.chunk_count > 0
    assert doc.extraction_backend == BACKEND_LEGACY
    assert doc.docling_json_path is None
    # And it is the *original* text, not a stub: the legacy parser really ran.
    assert "14 days" in "\n".join(await _chunk_texts(db_session, doc))


async def test_the_backend_lands_on_the_chunks_too(db_session: AsyncSession, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Provenance on the chunk, so a retrieved result is traceable without a join."""
    doc = await _document(db_session, tmp_path)
    with _enabled():
        await ingest_document(db_session, doc.id, docling_transport=_ok())
    rows = await db_session.execute(select(Chunk.meta).where(Chunk.document_id == doc.id))
    metas = list(rows.scalars().all())
    assert metas and all(m.get("backend") == BACKEND_DOCLING for m in metas)


# ── the persisted DoclingDocument ────────────────────────────────────────────────────────

async def test_the_structured_document_is_persisted_and_round_trips(
    db_session: AsyncSession, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    """docs/14 §3.4 — this is what makes re-chunking free instead of a full re-conversion."""
    doc = await _document(db_session, tmp_path)
    with _enabled():
        await ingest_document(db_session, doc.id, docling_transport=_ok())
    await db_session.refresh(doc)

    assert doc.docling_json_path is not None
    assert _read_json(doc.docling_json_path) == DOCLING_JSON


async def test_legacy_ingest_records_the_backend_and_no_json(
    db_session: AsyncSession, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    """Docling off — the default for every deployment — is unchanged behaviour, recorded."""
    doc = await _document(db_session, tmp_path)
    await ingest_document(db_session, doc.id)
    await db_session.refresh(doc)

    assert doc.status == "ready", doc.error_message
    assert doc.extraction_backend == BACKEND_LEGACY
    assert doc.docling_json_path is None


async def test_a_reingest_that_loses_structure_clears_the_stale_path(
    db_session: AsyncSession, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    """A path left pointing at a previous conversion is worse than no path at all.

    Re-ingesting with Docling down must not leave `docling_json_path` describing text that is
    no longer what the chunks were built from — a later re-chunk would silently rebuild from
    the wrong extraction.
    """
    doc = await _document(db_session, tmp_path)
    with _enabled():
        await ingest_document(db_session, doc.id, docling_transport=_ok())
    await db_session.refresh(doc)
    assert doc.docling_json_path is not None

    with _enabled():
        await ingest_document(db_session, doc.id, docling_transport=_down())
    await db_session.refresh(doc)
    assert doc.extraction_backend == BACKEND_LEGACY
    assert doc.docling_json_path is None
