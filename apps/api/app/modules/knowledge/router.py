"""Knowledge routes under /v1/knowledge."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.modules.knowledge import schemas, service
from app.modules.orgs.deps import OrgContext, current_org

router = APIRouter(prefix="/v1/knowledge", tags=["knowledge"])


# ── Knowledge bases ─────────────────────────────────────────────────────────────
@router.post("", response_model=schemas.KBOut, status_code=status.HTTP_201_CREATED)
async def create_kb(
    data: schemas.CreateKBRequest,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> schemas.KBOut:
    return await service.create_kb(session, ctx, data)


@router.get("", response_model=list[schemas.KBOut])
async def list_kbs(
    session: AsyncSession = Depends(get_session), ctx: OrgContext = Depends(current_org)
) -> list[schemas.KBOut]:
    return await service.list_kbs(session, ctx)


@router.get("/{kb_id}", response_model=schemas.KBOut)
async def get_kb(
    kb_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> schemas.KBOut:
    return await service.get_kb(session, ctx, kb_id)


@router.patch("/{kb_id}", response_model=schemas.KBOut)
async def update_kb(
    kb_id: uuid.UUID,
    data: schemas.UpdateKBRequest,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> schemas.KBOut:
    return await service.update_kb(session, ctx, kb_id, data)


@router.delete("/{kb_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_kb(
    kb_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> None:
    await service.delete_kb(session, ctx, kb_id)


# ── Documents ───────────────────────────────────────────────────────────────────
@router.post("/{kb_id}/documents", response_model=schemas.DocumentOut, status_code=status.HTTP_201_CREATED)
async def create_document(
    kb_id: uuid.UUID,
    data: schemas.CreateDocumentRequest,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> schemas.DocumentOut:
    return await service.create_document(session, ctx, kb_id, data)


@router.post("/{kb_id}/documents/upload", response_model=schemas.DocumentOut, status_code=status.HTTP_201_CREATED)
async def upload_document(
    kb_id: uuid.UUID,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> schemas.DocumentOut:
    data = await file.read()
    return await service.upload_document(
        session,
        ctx,
        kb_id,
        filename=file.filename or "upload.bin",
        mime_type=file.content_type,
        data=data,
    )


@router.get("/{kb_id}/documents", response_model=list[schemas.DocumentOut])
async def list_documents(
    kb_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> list[schemas.DocumentOut]:
    return await service.list_documents(session, ctx, kb_id)


@router.get("/documents/{document_id}", response_model=schemas.DocumentOut)
async def get_document(
    document_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> schemas.DocumentOut:
    return await service.get_document(session, ctx, document_id)


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> None:
    await service.delete_document(session, ctx, document_id)


@router.post("/documents/{document_id}/reingest", response_model=schemas.DocumentOut)
async def reingest_document(
    document_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> schemas.DocumentOut:
    return await service.reingest_document(session, ctx, document_id)


@router.get("/documents/{document_id}/chunks", response_model=list[schemas.ChunkOut])
async def list_chunks(
    document_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> list[schemas.ChunkOut]:
    return await service.list_chunks(session, ctx, document_id)


# ── Retrieval ───────────────────────────────────────────────────────────────────
@router.post("/{kb_id}/search", response_model=schemas.SearchResponse)
async def search_kb(
    kb_id: uuid.UUID,
    data: schemas.SearchRequest,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> schemas.SearchResponse:
    return await service.search_kb(session, ctx, kb_id, data)
