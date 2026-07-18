"""API key routes under /v1/apikeys (docs/04 §API keys)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.modules.apikeys import schemas, service
from app.modules.orgs.deps import OrgContext, current_org

router = APIRouter(prefix="/v1/apikeys", tags=["apikeys"])


@router.post("", response_model=schemas.ApiKeyCreated, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    data: schemas.CreateApiKeyRequest,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> schemas.ApiKeyCreated:
    return await service.create_api_key(session, ctx, data)


@router.get("", response_model=list[schemas.ApiKeyOut])
async def list_api_keys(
    session: AsyncSession = Depends(get_session), ctx: OrgContext = Depends(current_org)
) -> list[schemas.ApiKeyOut]:
    return await service.list_api_keys(session, ctx)


@router.post("/{key_id}/revoke", response_model=schemas.ApiKeyOut)
async def revoke_api_key(
    key_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> schemas.ApiKeyOut:
    return await service.revoke_api_key(session, ctx, key_id)


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_api_key(
    key_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> None:
    await service.delete_api_key(session, ctx, key_id)
