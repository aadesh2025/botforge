"""Provider-credential routes under /v1/credentials."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.modules.credentials import schemas, service
from app.modules.orgs.deps import OrgContext, current_org

router = APIRouter(prefix="/v1/credentials", tags=["credentials"])


@router.get("/providers", response_model=list[schemas.ProviderInfo])
async def list_providers(_: OrgContext = Depends(current_org)) -> list[schemas.ProviderInfo]:
    return service.list_providers()


@router.get("", response_model=list[schemas.CredentialOut])
async def list_credentials(
    session: AsyncSession = Depends(get_session), ctx: OrgContext = Depends(current_org)
) -> list[schemas.CredentialOut]:
    return await service.list_credentials(session, ctx)


@router.post("", response_model=schemas.CredentialOut, status_code=status.HTTP_201_CREATED)
async def create_credential(
    data: schemas.CredentialCreate,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> schemas.CredentialOut:
    return await service.create_credential(session, ctx, data)


@router.patch("/{cred_id}", response_model=schemas.CredentialOut)
async def update_credential(
    cred_id: uuid.UUID,
    data: schemas.CredentialUpdate,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> schemas.CredentialOut:
    return await service.update_credential(session, ctx, cred_id, data)


@router.delete("/{cred_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_credential(
    cred_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> None:
    await service.delete_credential(session, ctx, cred_id)


@router.post("/{cred_id}/test", response_model=schemas.CredentialTestResult)
async def test_credential(
    cred_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> schemas.CredentialTestResult:
    return await service.test_credential(session, ctx, cred_id)
