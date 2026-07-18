"""Ingestion pipeline: load → chunk → embed → store (docs/06 §2).

This is a plain async function so it is directly testable against the transaction-rolled-back
test session. The Celery task in `app.worker.tasks` wraps it with its own committing session.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import httpx
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.llm.registry import build_embedding_provider
from app.models import Chunk, Document, KnowledgeBase
from app.rag import loaders
from app.rag.chunking import chunk_text
from app.webhooks.dispatch import emit_event

log = get_logger("rag.ingest")

_EMBED_BATCH = 64


def _read_file_source(storage_path: str, filename: str | None, mime_type: str | None) -> str:
    path = Path(storage_path)
    if not path.exists():
        raise loaders.LoaderError(f"Stored file is missing: {path}")
    data = path.read_bytes()
    return loaders.load_bytes(data, filename=filename, mime_type=mime_type)


async def _read_source(document: Document, *, url_transport: httpx.AsyncBaseTransport | None) -> str:
    if document.source_type == "url":
        if not document.source_url:
            raise loaders.LoaderError("Document has no source URL.")
        return await loaders.load_url(document.source_url, transport=url_transport)
    if not document.storage_path:
        raise loaders.LoaderError("Document has no stored file.")
    return _read_file_source(document.storage_path, document.filename, document.mime_type)


async def ingest_document(
    session: AsyncSession,
    document_id: uuid.UUID,
    *,
    url_transport: httpx.AsyncBaseTransport | None = None,
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
        text = await _read_source(document, url_transport=url_transport)
        if not text.strip():
            raise loaders.LoaderError("No extractable text in document.")

        chunks = chunk_text(
            text,
            kb.chunk_size,
            kb.chunk_overlap,
            metadata={"filename": document.filename, "source_url": document.source_url},
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
