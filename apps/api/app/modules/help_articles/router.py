"""Help Center routes: authenticated authoring under /v1/help-articles."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.modules.help_articles import schemas, service
from app.modules.orgs.deps import OrgContext, current_org

router = APIRouter(prefix="/v1/help-articles", tags=["help-center"])


@router.get("", response_model=list[schemas.HelpArticleOut])
async def list_articles(
    agent_id: uuid.UUID | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> list[schemas.HelpArticleOut]:
    return await service.list_articles(session, ctx, agent_id)


@router.post("", response_model=schemas.HelpArticleOut, status_code=status.HTTP_201_CREATED)
async def create_article(
    data: schemas.CreateHelpArticleRequest,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> schemas.HelpArticleOut:
    return await service.create_article(session, ctx, data)


@router.get("/{article_id}", response_model=schemas.HelpArticleOut)
async def get_article(
    article_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> schemas.HelpArticleOut:
    return await service.get_article(session, ctx, article_id)


@router.patch("/{article_id}", response_model=schemas.HelpArticleOut)
async def update_article(
    article_id: uuid.UUID,
    data: schemas.UpdateHelpArticleRequest,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> schemas.HelpArticleOut:
    return await service.update_article(session, ctx, article_id, data)


@router.delete("/{article_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_article(
    article_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> None:
    await service.delete_article(session, ctx, article_id)
