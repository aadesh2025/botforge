"""Campaign routes under /v1/campaigns."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.modules.campaigns import schemas, service
from app.modules.orgs.deps import OrgContext, current_org

router = APIRouter(prefix="/v1/campaigns", tags=["campaigns"])


@router.get("", response_model=list[schemas.CampaignOut])
async def list_campaigns(
    agent_id: uuid.UUID | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> list[schemas.CampaignOut]:
    return await service.list_campaigns(session, ctx, agent_id)


@router.post("", response_model=schemas.CampaignOut, status_code=status.HTTP_201_CREATED)
async def create_campaign(
    data: schemas.CreateCampaignRequest,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> schemas.CampaignOut:
    return await service.create_campaign(session, ctx, data)


@router.patch("/{campaign_id}", response_model=schemas.CampaignOut)
async def update_campaign(
    campaign_id: uuid.UUID,
    data: schemas.UpdateCampaignRequest,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> schemas.CampaignOut:
    return await service.update_campaign(session, ctx, campaign_id, data)


@router.delete("/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_campaign(
    campaign_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> None:
    await service.delete_campaign(session, ctx, campaign_id)
