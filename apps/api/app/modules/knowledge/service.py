"""Knowledge-base, document, ingestion, and retrieval service."""

from __future__ import annotations

import datetime as dt
import uuid
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import rbac
from app.core.config import settings
from app.core.errors import AppError
from app.core.logging import get_logger
from app.llm.registry import build_embedding_provider
from app.models import Chunk, Document, KnowledgeBase
from app.modules.knowledge import schemas
from app.modules.orgs.deps import OrgContext
from app.rag import retrieval
from app.worker.tasks import enqueue_document_ingestion

log = get_logger("knowledge")


# ── Knowledge bases ─────────────────────────────────────────────────────────────
async def _get_kb(session: AsyncSession, ctx: OrgContext, kb_id: uuid.UUID) -> KnowledgeBase:
    kb = await session.get(KnowledgeBase, kb_id)
    if kb is None or kb.organization_id != ctx.org.id or kb.deleted_at is not None:
        raise AppError("kb.not_found", "Knowledge base not found.", 404)
    return kb


async def _doc_count(session: AsyncSession, kb_id: uuid.UUID) -> int:
    stmt = select(func.count()).select_from(Document).where(Document.knowledge_base_id == kb_id)
    return int((await session.execute(stmt)).scalar_one())


async def _kb_out(session: AsyncSession, kb: KnowledgeBase) -> schemas.KBOut:
    return schemas.KBOut(
        id=kb.id,
        name=kb.name,
        description=kb.description,
        embedding_provider=kb.embedding_provider,
        embedding_model=kb.embedding_model,
        chunk_size=kb.chunk_size,
        chunk_overlap=kb.chunk_overlap,
        document_count=await _doc_count(session, kb.id),
        created_at=kb.created_at,
        updated_at=kb.updated_at,
    )


async def create_kb(session: AsyncSession, ctx: OrgContext, data: schemas.CreateKBRequest) -> schemas.KBOut:
    rbac.require_permission(ctx.role, rbac.KB_MANAGE)
    kb = KnowledgeBase(
        organization_id=ctx.org.id,
        name=data.name,
        description=data.description,
        embedding_provider=data.embedding_provider,
        embedding_model=data.embedding_model,
        chunk_size=data.chunk_size,
        chunk_overlap=data.chunk_overlap,
        created_by=ctx.user.id,
    )
    session.add(kb)
    await session.flush()
    return await _kb_out(session, kb)


async def list_kbs(session: AsyncSession, ctx: OrgContext) -> list[schemas.KBOut]:
    rbac.require_permission(ctx.role, rbac.READ)
    stmt = (
        select(KnowledgeBase)
        .where(KnowledgeBase.organization_id == ctx.org.id, KnowledgeBase.deleted_at.is_(None))
        .order_by(KnowledgeBase.created_at.desc())
    )
    kbs = (await session.execute(stmt)).scalars().all()
    return [await _kb_out(session, kb) for kb in kbs]


async def get_kb(session: AsyncSession, ctx: OrgContext, kb_id: uuid.UUID) -> schemas.KBOut:
    rbac.require_permission(ctx.role, rbac.READ)
    return await _kb_out(session, await _get_kb(session, ctx, kb_id))


async def update_kb(
    session: AsyncSession, ctx: OrgContext, kb_id: uuid.UUID, data: schemas.UpdateKBRequest
) -> schemas.KBOut:
    rbac.require_permission(ctx.role, rbac.KB_MANAGE)
    kb = await _get_kb(session, ctx, kb_id)
    if data.name is not None:
        kb.name = data.name
    if data.description is not None:
        kb.description = data.description
    if data.chunk_size is not None:
        kb.chunk_size = data.chunk_size
    if data.chunk_overlap is not None:
        kb.chunk_overlap = data.chunk_overlap
    return await _kb_out(session, kb)


async def delete_kb(session: AsyncSession, ctx: OrgContext, kb_id: uuid.UUID) -> None:
    rbac.require_permission(ctx.role, rbac.KB_MANAGE)
    kb = await _get_kb(session, ctx, kb_id)
    kb.deleted_at = dt.datetime.now(tz=dt.UTC)


# ── Documents ───────────────────────────────────────────────────────────────────
def _doc_out(doc: Document) -> schemas.DocumentOut:
    return schemas.DocumentOut(
        id=doc.id,
        knowledge_base_id=doc.knowledge_base_id,
        source_type=doc.source_type,
        filename=doc.filename,
        mime_type=doc.mime_type,
        size_bytes=doc.size_bytes,
        source_url=doc.source_url,
        status=doc.status,
        error_message=doc.error_message,
        chunk_count=doc.chunk_count,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


def _store_file(org_id: uuid.UUID, document_id: uuid.UUID, filename: str | None, data: bytes) -> str:
    """Persist bytes under the upload dir and return the storage path."""
    suffix = Path(filename or "").suffix or ".txt"
    dest_dir = Path(settings.upload_dir) / str(org_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{document_id}{suffix}"
    dest.write_bytes(data)
    return str(dest)


def _remove_file(storage_path: str) -> None:
    Path(storage_path).unlink(missing_ok=True)


async def _get_document(session: AsyncSession, ctx: OrgContext, document_id: uuid.UUID) -> Document:
    doc = await session.get(Document, document_id)
    if doc is None or doc.organization_id != ctx.org.id:
        raise AppError("kb.document_not_found", "Document not found.", 404)
    return doc


async def create_document(
    session: AsyncSession, ctx: OrgContext, kb_id: uuid.UUID, data: schemas.CreateDocumentRequest
) -> schemas.DocumentOut:
    rbac.require_permission(ctx.role, rbac.KB_MANAGE)
    kb = await _get_kb(session, ctx, kb_id)

    doc = Document(
        knowledge_base_id=kb.id,
        organization_id=ctx.org.id,
        source_type=data.source_type,
        status="queued",
        created_by=ctx.user.id,
    )
    if data.source_type == "text":
        if not data.text or not data.text.strip():
            raise AppError("kb.text_required", "text is required for a text document.", 400)
        doc.filename = data.filename or "text-snippet.txt"
        doc.mime_type = "text/plain"
        raw = data.text.encode("utf-8")
        doc.size_bytes = len(raw)
        session.add(doc)
        await session.flush()
        doc.storage_path = _store_file(ctx.org.id, doc.id, doc.filename, raw)
    else:  # url
        if not data.url:
            raise AppError("kb.url_required", "url is required for a url document.", 400)
        doc.source_url = data.url
        doc.filename = data.filename or data.url
        session.add(doc)
        await session.flush()

    enqueue_document_ingestion(doc.id)
    return _doc_out(doc)


async def upload_document(
    session: AsyncSession,
    ctx: OrgContext,
    kb_id: uuid.UUID,
    *,
    filename: str,
    mime_type: str | None,
    data: bytes,
) -> schemas.DocumentOut:
    rbac.require_permission(ctx.role, rbac.KB_MANAGE)
    kb = await _get_kb(session, ctx, kb_id)
    if not data:
        raise AppError("kb.empty_file", "Uploaded file is empty.", 400)
    doc = Document(
        knowledge_base_id=kb.id,
        organization_id=ctx.org.id,
        source_type="file",
        filename=filename,
        mime_type=mime_type,
        size_bytes=len(data),
        status="queued",
        created_by=ctx.user.id,
    )
    session.add(doc)
    await session.flush()
    doc.storage_path = _store_file(ctx.org.id, doc.id, filename, data)
    enqueue_document_ingestion(doc.id)
    return _doc_out(doc)


async def list_documents(session: AsyncSession, ctx: OrgContext, kb_id: uuid.UUID) -> list[schemas.DocumentOut]:
    rbac.require_permission(ctx.role, rbac.READ)
    await _get_kb(session, ctx, kb_id)
    stmt = (
        select(Document)
        .where(Document.knowledge_base_id == kb_id, Document.organization_id == ctx.org.id)
        .order_by(Document.created_at.desc())
    )
    return [_doc_out(d) for d in (await session.execute(stmt)).scalars().all()]


async def get_document(session: AsyncSession, ctx: OrgContext, document_id: uuid.UUID) -> schemas.DocumentOut:
    rbac.require_permission(ctx.role, rbac.READ)
    return _doc_out(await _get_document(session, ctx, document_id))


async def delete_document(session: AsyncSession, ctx: OrgContext, document_id: uuid.UUID) -> None:
    rbac.require_permission(ctx.role, rbac.KB_MANAGE)
    doc = await _get_document(session, ctx, document_id)
    if doc.storage_path:
        _remove_file(doc.storage_path)
    await session.delete(doc)  # chunks cascade via FK


async def reingest_document(session: AsyncSession, ctx: OrgContext, document_id: uuid.UUID) -> schemas.DocumentOut:
    rbac.require_permission(ctx.role, rbac.KB_MANAGE)
    doc = await _get_document(session, ctx, document_id)
    doc.status = "queued"
    doc.error_message = None
    await session.flush()
    enqueue_document_ingestion(doc.id)
    return _doc_out(doc)


async def list_chunks(session: AsyncSession, ctx: OrgContext, document_id: uuid.UUID) -> list[schemas.ChunkOut]:
    rbac.require_permission(ctx.role, rbac.READ)
    doc = await _get_document(session, ctx, document_id)
    stmt = select(Chunk).where(Chunk.document_id == doc.id).order_by(Chunk.ordinal.asc())
    return [
        schemas.ChunkOut(
            id=c.id, ordinal=c.ordinal, content=c.content, token_count=c.token_count, metadata=c.meta or {}
        )
        for c in (await session.execute(stmt)).scalars().all()
    ]


# ── Retrieval ───────────────────────────────────────────────────────────────────
async def search_kb(
    session: AsyncSession, ctx: OrgContext, kb_id: uuid.UUID, data: schemas.SearchRequest
) -> schemas.SearchResponse:
    rbac.require_permission(ctx.role, rbac.READ)
    kb = await _get_kb(session, ctx, kb_id)
    embedder = build_embedding_provider(kb.embedding_provider, kb.embedding_model)
    citations = await retrieval.search(
        session,
        ctx.org.id,
        [kb.id],
        data.query,
        embedder,
        top_k=data.top_k,
        score_threshold=data.score_threshold,
        hybrid=data.hybrid,
    )
    return schemas.SearchResponse(query=data.query, citations=citations)
