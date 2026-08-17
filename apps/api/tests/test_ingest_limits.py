"""Page caps and the retention of the persisted DoclingDocument (docs/14 K5-2, K5-3)."""

from __future__ import annotations

import io
import json
import uuid
from pathlib import Path

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import Document, KnowledgeBase, Organization
from app.rag import loaders
from app.rag.ingest import ingest_document

DOCLING_JSON = {"schema_name": "DoclingDocument", "name": "policy"}


def _exists(path: str | Path) -> bool:
    """Sync, so an async test does not trip ruff ASYNC240 on a local stat."""
    return Path(path).exists()


def _read_json(path: str | Path) -> object:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _pdf(pages: int) -> bytes:
    """A real, minimal PDF with `pages` pages — pypdf has to be able to count them."""
    pytest.importorskip("pypdf")
    from pypdf import PdfWriter

    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


async def _document(
    session: AsyncSession, tmp_path: Path, *, name: str, data: bytes
) -> Document:
    org = Organization(name="Limits Org", slug=f"limits-{uuid.uuid4().hex[:8]}")
    session.add(org)
    await session.flush()
    kb = KnowledgeBase(
        organization_id=org.id, name="KB", embedding_provider="fake", embedding_model="fake-embed"
    )
    session.add(kb)
    await session.flush()
    path = tmp_path / name
    path.write_bytes(data)
    doc = Document(
        knowledge_base_id=kb.id,
        organization_id=org.id,
        source_type="file",
        filename=name,
        mime_type="application/pdf" if name.endswith(".pdf") else "text/plain",
        status="queued",
        storage_path=str(path),
    )
    session.add(doc)
    await session.flush()
    return doc


# ── K5-2: the page cap ───────────────────────────────────────────────────────────────────

def test_page_count_is_read_without_extracting_text() -> None:
    assert loaders.pdf_page_count(_pdf(7)) == 7


def test_page_count_of_a_non_pdf_is_none_not_an_exception() -> None:
    """A page cap must not be the thing that decides a corrupt file cannot be ingested — the
    extractor owns that call, and it has a better error message for it."""
    assert loaders.pdf_page_count(b"this is not a pdf") is None
    assert loaders.pdf_page_count(b"") is None


async def test_an_over_length_pdf_fails_with_the_limit_in_the_message(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    doc = await _document(db_session, tmp_path, name="huge.pdf", data=_pdf(6))
    previous = settings.max_pdf_pages
    settings.max_pdf_pages = 5
    try:
        await ingest_document(db_session, doc.id)
    finally:
        settings.max_pdf_pages = previous

    await db_session.refresh(doc)
    assert doc.status == "failed"
    # Both numbers, because "too large" is not something a client can act on.
    assert "6 pages" in (doc.error_message or "")
    assert "800" not in (doc.error_message or "")
    assert "5" in (doc.error_message or "")


async def test_a_pdf_under_the_cap_is_unaffected(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    """The other direction. A cap that rejects everything passes a rejection-only test."""
    doc = await _document(db_session, tmp_path, name="fine.pdf", data=_pdf(2))
    previous = settings.max_pdf_pages
    settings.max_pdf_pages = 5
    try:
        await ingest_document(db_session, doc.id)
    finally:
        settings.max_pdf_pages = previous
    await db_session.refresh(doc)
    # A blank PDF has no extractable text, so it fails — but on *extraction*, not on the cap.
    assert "pages and the limit is" not in (doc.error_message or "")


async def test_the_cap_never_looks_at_a_non_pdf(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    doc = await _document(db_session, tmp_path, name="notes.txt", data=b"Refunds take 14 days.")
    previous = settings.max_pdf_pages
    settings.max_pdf_pages = 1
    try:
        await ingest_document(db_session, doc.id)
    finally:
        settings.max_pdf_pages = previous
    await db_session.refresh(doc)
    assert doc.status == "ready", doc.error_message


async def test_a_cap_of_zero_disables_the_check(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    doc = await _document(db_session, tmp_path, name="huge.pdf", data=_pdf(4))
    previous = settings.max_pdf_pages
    settings.max_pdf_pages = 0
    try:
        await ingest_document(db_session, doc.id)
    finally:
        settings.max_pdf_pages = previous
    await db_session.refresh(doc)
    assert "pages and the limit is" not in (doc.error_message or "")


# ── K5-3: retention ──────────────────────────────────────────────────────────────────────

async def test_a_reingest_without_structure_deletes_the_orphaned_json(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    """Clearing the column is not enough.

    The file holds the document's full text. Once the column no longer points at it, nothing
    ever deletes it — `delete_document` deletes by that path — so it outlives the document it
    came from. That is the answer to a data-subject request being wrong.
    """
    doc = await _document(db_session, tmp_path, name="policy.txt", data=b"Refunds take 14 days.")
    ok = httpx.MockTransport(
        lambda r: httpx.Response(
            200, json={"document": {"md_content": "# Policy\n\nRefunds.", "json_content": DOCLING_JSON}}
        )
    )
    previous = (settings.docling_enabled, settings.docling_endpoint)
    settings.docling_enabled, settings.docling_endpoint = True, "http://docling:5001"
    try:
        await ingest_document(db_session, doc.id, docling_transport=ok)
        await db_session.refresh(doc)
        json_path = Path(doc.docling_json_path or "")
        assert _exists(json_path)
        assert _read_json(json_path) == DOCLING_JSON

        # Now re-ingest with Docling down: falls back to legacy, so there is no structure.
        down = httpx.MockTransport(lambda r: httpx.Response(503, text="unavailable"))
        await ingest_document(db_session, doc.id, docling_transport=down)
    finally:
        settings.docling_enabled, settings.docling_endpoint = previous

    await db_session.refresh(doc)
    assert doc.docling_json_path is None
    assert not _exists(json_path), "the extraction outlived the chunks it produced"


async def test_deleting_a_document_deletes_its_persisted_extraction(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    """K5-3's retention policy: the JSON's lifetime is the document's.

    `delete_document` removed `storage_path` and nothing else, so the structured extraction —
    the document's full text, element by element — stayed on disk after the client deleted it.
    """
    from app.modules.knowledge import service

    doc = await _document(db_session, tmp_path, name="policy.txt", data=b"Refunds take 14 days.")
    ok = httpx.MockTransport(
        lambda r: httpx.Response(
            200, json={"document": {"md_content": "# Policy\n\nRefunds.", "json_content": DOCLING_JSON}}
        )
    )
    previous = (settings.docling_enabled, settings.docling_endpoint)
    settings.docling_enabled, settings.docling_endpoint = True, "http://docling:5001"
    try:
        await ingest_document(db_session, doc.id, docling_transport=ok)
    finally:
        settings.docling_enabled, settings.docling_endpoint = previous
    await db_session.refresh(doc)

    upload = Path(doc.storage_path or "")
    extraction = Path(doc.docling_json_path or "")
    assert _exists(upload) and _exists(extraction)

    service._remove_document_files(doc)

    assert not _exists(upload)
    assert not _exists(extraction), "a deleted document left its full text on disk"
