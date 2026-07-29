"""Macro routes under /v1/macros, plus the run endpoint on a conversation."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.modules.macros import schemas, service
from app.modules.orgs.deps import OrgContext, current_org

router = APIRouter(prefix="/v1/macros", tags=["macros"])


@router.get("", response_model=list[schemas.MacroOut])
async def list_macros(
    session: AsyncSession = Depends(get_session), ctx: OrgContext = Depends(current_org)
) -> list[schemas.MacroOut]:
    return await service.list_macros(session, ctx)


@router.post("", response_model=schemas.MacroOut, status_code=status.HTTP_201_CREATED)
async def create_macro(
    data: schemas.CreateMacroRequest,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> schemas.MacroOut:
    return await service.create_macro(session, ctx, data)


@router.patch("/{macro_id}", response_model=schemas.MacroOut)
async def update_macro(
    macro_id: uuid.UUID,
    data: schemas.UpdateMacroRequest,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> schemas.MacroOut:
    return await service.update_macro(session, ctx, macro_id, data)


@router.delete("/{macro_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_macro(
    macro_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> None:
    await service.delete_macro(session, ctx, macro_id)


# Lives under the conversation it acts on, alongside the manual reply/tag/assign routes.
inbox_router = APIRouter(prefix="/v1/inbox", tags=["macros"])


@inbox_router.post("/conversations/{cid}/macros/{macro_id}", response_model=schemas.MacroRunResult)
async def run_macro(
    cid: uuid.UUID,
    macro_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> schemas.MacroRunResult:
    return await service.run_macro(session, ctx, cid, macro_id)
