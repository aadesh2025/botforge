"""Analytics routes under /v1/analytics (docs/04 §Analytics)."""

from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.modules.analytics import schemas, service
from app.modules.orgs.deps import OrgContext, current_org

router = APIRouter(prefix="/v1/analytics", tags=["analytics"])


@router.get("/overview", response_model=schemas.Overview)
async def overview(
    agent_id: uuid.UUID | None = Query(default=None),
    from_date: dt.date | None = Query(default=None, alias="from"),
    to_date: dt.date | None = Query(default=None, alias="to"),
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> schemas.Overview:
    return await service.overview(session, ctx, agent_id, from_date, to_date)


@router.get("/usage", response_model=list[schemas.UsageBucket])
async def usage(
    agent_id: uuid.UUID | None = Query(default=None),
    from_date: dt.date | None = Query(default=None, alias="from"),
    to_date: dt.date | None = Query(default=None, alias="to"),
    group_by: str = Query(default="day", pattern="^(day|provider|model)$"),
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> list[schemas.UsageBucket]:
    return await service.usage(session, ctx, agent_id, from_date, to_date, group_by)


@router.get("/latency", response_model=schemas.LatencyStats)
async def latency(
    agent_id: uuid.UUID | None = Query(default=None),
    from_date: dt.date | None = Query(default=None, alias="from"),
    to_date: dt.date | None = Query(default=None, alias="to"),
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> schemas.LatencyStats:
    return await service.latency(session, ctx, agent_id, from_date, to_date)


@router.get("/top-questions", response_model=list[schemas.QuestionCount])
async def top_questions(
    agent_id: uuid.UUID | None = Query(default=None),
    from_date: dt.date | None = Query(default=None, alias="from"),
    to_date: dt.date | None = Query(default=None, alias="to"),
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> list[schemas.QuestionCount]:
    return await service.top_questions(session, ctx, agent_id, from_date, to_date)


@router.get("/unanswered", response_model=list[schemas.QuestionCount])
async def unanswered(
    agent_id: uuid.UUID | None = Query(default=None),
    from_date: dt.date | None = Query(default=None, alias="from"),
    to_date: dt.date | None = Query(default=None, alias="to"),
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> list[schemas.QuestionCount]:
    return await service.unanswered(session, ctx, agent_id, from_date, to_date)


@router.get("/export")
async def export_csv(
    type: str = Query(default="usage", pattern="^(usage|conversations)$"),
    agent_id: uuid.UUID | None = Query(default=None),
    from_date: dt.date | None = Query(default=None, alias="from"),
    to_date: dt.date | None = Query(default=None, alias="to"),
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> PlainTextResponse:
    csv = await service.export_csv(session, ctx, type, agent_id, from_date, to_date)
    return PlainTextResponse(
        csv,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{type}.csv"'},
    )
