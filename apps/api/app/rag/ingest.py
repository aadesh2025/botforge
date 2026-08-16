"""Ingestion pipeline: load → chunk → embed → store (docs/06 §2).

This is a plain async function so it is directly testable against the transaction-rolled-back
test session. The Celery task in `app.worker.tasks` wraps it with its own committing session.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat.pii import scan_document_text
from app.core.logging import get_logger
from app.llm.registry import build_embedding_provider
from app.models import Chunk, Document, KnowledgeBase
from app.rag import converters, loaders
from app.rag.chunking import chunk_text
from app.webhooks.dispatch import emit_event

log = get_logger("rag.ingest")

_EMBED_BATCH = 64


def _stored_bytes(storage_path: str) -> bytes:
    """Read the uploaded file. Sync on purpose — see below.

    Kept out of the async path so the blocking read is honest rather than hidden inside a
    coroutine (ruff ASYNC240). It runs in the Celery ingest worker, where blocking on a local
    file for a few milliseconds is the expected shape of the job, not a latency problem.
    """
    path = Path(storage_path)
    if not path.exists():
        raise loaders.LoaderError(f"Stored file is missing: {path}")
    return path.read_bytes()


async def _read_source(
    document: Document,
    *,
    url_transport: httpx.AsyncBaseTransport | None,
    docling_transport: httpx.AsyncBaseTransport | None = None,
) -> converters.ConvertedDocument:
    if document.source_type == "url":
        if not document.source_url:
            raise loaders.LoaderError("Document has no source URL.")
        # URL ingest deliberately stays on trafilatura and does NOT go through Docling. The
        # SSRF controls in `loaders.load_url` (scheme check, private/loopback rejection) are
        # what stand between a visitor-suppliable URL and the internal network, and handing the
        # URL to docling-serve to fetch would route around them entirely — docs/14 §9's rule
        # that a new code path must not bypass an existing control. trafilatura also already
        # produces structured markdown for HTML, which is what Docling would add.
        text = await loaders.load_url(document.source_url, transport=url_transport)
        return converters.ConvertedDocument(text=text, backend=converters.BACKEND_LEGACY)
    if not document.storage_path:
        raise loaders.LoaderError("Document has no stored file.")
    data = _stored_bytes(document.storage_path)
    return await converters.convert_with_fallback(
        data,
        filename=document.filename,
        mime_type=document.mime_type,
        transport=docling_transport,
    )


def _persist_docling_json(document: Document, payload: dict[str, Any]) -> str | None:
    """Write the `DoclingDocument` beside the source file. Never fails the ingest.

    Losing the structured form costs a future re-chunk a re-conversion (docs/14 §8: "fall back
    to full re-conversion; log it"). Losing the *document* because a disk was full would be a
    far worse trade, so this is best-effort by design.
    """
    if not document.storage_path:
        return None
    path = Path(document.storage_path).with_suffix(".docling.json")
    try:
        path.write_text(json.dumps(payload), encoding="utf-8")
    except OSError as exc:
        log.warning(
            "docling_json_persist_failed",
            document_id=str(document.id),
            error=str(exc)[:200],
            impact="re-chunking this document will need a full re-conversion",
        )
        return None
    return str(path)


async def ingest_document(
    session: AsyncSession,
    document_id: uuid.UUID,
    *,
    url_transport: httpx.AsyncBaseTransport | None = None,
    docling_transport: httpx.AsyncBaseTransport | None = None,
) -> Document:
    """Parse, chunk, embed and store a document. Sets status ready|failed; never raises."""
    document = await session.get(Document, document_id)
    if document is None:
        raise loaders.LoaderError(f"Document {document_id} not found.")
    kb = await session.get(KnowledgeBase, document.knowledge_base_id)
    if kb is None:
        raise loaders.LoaderError("Knowledge base not found.")

    document.status = "processing"
    document.error_message = None
    await session.flush()

    try:
        converted = await _read_source(
            document, url_transport=url_transport, docling_transport=docling_transport
        )
        text = converted.text
        if not text.strip():
            raise loaders.LoaderError("No extractable text in document.")
        document.extraction_backend = converted.backend
        # Persisted before chunking, so a later re-chunk (K2-4) can skip conversion entirely.
        document.docling_json_path = (
            _persist_docling_json(document, converted.document) if converted.document else None
        )

        # Scan before chunking, so a contact detail split across a chunk boundary is still
        # counted once against the whole document (docs/11 Phase B, §6).
        document.pii_flags = scan_document_text(text)
        if document.pii_flags:
            # Counts only — never the values. A PII report that echoes the PII is the same
            # leak in a different place.
            log.warning(
                "document_pii_detected",
                document_id=str(document.id),
                organization_id=str(document.organization_id),
                flags=document.pii_flags,
            )

        chunks = chunk_text(
            text,
            kb.chunk_size,
            kb.chunk_overlap,
            metadata={
                "filename": document.filename,
                "source_url": document.source_url,
                # Provenance on the chunk itself, so a retrieved result can be traced to the
                # extractor that produced it without a join back to `documents`.
                "backend": converted.backend,
            },
        )
        if not chunks:
            raise loaders.LoaderError("Document produced no chunks.")

        embedder = build_embedding_provider(kb.embedding_provider, kb.embedding_model)
        vectors: list[list[float]] = []
        for i in range(0, len(chunks), _EMBED_BATCH):
            batch = [c.content for c in chunks[i : i + _EMBED_BATCH]]
            vectors.extend(await embedder.embed(batch))

        # Reingest: clear any prior chunks for this document.
        await session.execute(delete(Chunk).where(Chunk.document_id == document.id))
        for chunk, vector in zip(chunks, vectors, strict=True):
            session.add(
                Chunk(
                    document_id=document.id,
                    knowledge_base_id=document.knowledge_base_id,
                    organization_id=document.organization_id,
                    ordinal=chunk.ordinal,
                    content=chunk.content,
                    token_count=chunk.token_count,
                    meta=chunk.metadata,
                    embedding=vector,
                )
            )
        document.status = "ready"
        document.chunk_count = len(chunks)
        document.error_message = None
        await session.flush()
        await emit_event(
            session, document.organization_id, "document.ready",
            {"document_id": str(document.id), "chunks": len(chunks)},
        )
        log.info("document_ingested", document_id=str(document.id), chunks=len(chunks))
    except Exception as exc:  # record failure, don't crash the worker
        document.status = "failed"
        document.error_message = str(exc)[:1000]
        document.chunk_count = 0
        await session.flush()
        await emit_event(
            session, document.organization_id, "document.failed",
            {"document_id": str(document.id), "error": str(exc)[:200]},
        )
        log.warning("document_ingest_failed", document_id=str(document.id), error=str(exc))
    return document
