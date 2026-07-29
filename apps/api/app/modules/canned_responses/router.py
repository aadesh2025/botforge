"""Canned response routes under /v1/canned-responses."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.modules.canned_responses import schemas, service
from app.modules.orgs.deps import OrgContext, current_org

router = APIRouter(prefix="/v1/canned-responses", tags=["canned-responses"])


@router.get("", response_model=list[schemas.CannedResponseOut])
async def list_canned_responses(
    q: str | None = Query(default=None, description="Filter by shortcut prefix/substring."),
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> list[schemas.CannedResponseOut]:
    return await service.list_canned_responses(session, ctx, q)


@router.post("", response_model=schemas.CannedResponseOut, status_code=status.HTTP_201_CREATED)
async def create_canned_response(
    data: schemas.CreateCannedResponseRequest,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> schemas.CannedResponseOut:
    return await service.create_canned_response(session, ctx, data)


@router.patch("/{cr_id}", response_model=schemas.CannedResponseOut)
async def update_canned_response(
    cr_id: uuid.UUID,
    data: schemas.UpdateCannedResponseRequest,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> schemas.CannedResponseOut:
    return await service.update_canned_response(session, ctx, cr_id, data)


@router.delete("/{cr_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_canned_response(
    cr_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> None:
    await service.delete_canned_response(session, ctx, cr_id)
