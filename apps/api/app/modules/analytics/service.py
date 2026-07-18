"""Analytics aggregation — computed live from messages/conversations/handoffs (org-scoped)."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import Date, cast, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.selectable import Select

from app.core import rbac
from app.models import Conversation, Handoff, Message
from app.modules.analytics import schemas
from app.modules.orgs.deps import OrgContext


def _range(from_date: dt.date | None, to_date: dt.date | None) -> tuple[dt.datetime, dt.datetime]:
    today = dt.datetime.now(tz=dt.UTC).date()
    start = from_date or (today - dt.timedelta(days=30))
    end = to_date or today
    start_dt = dt.datetime.combine(start, dt.time.min, tzinfo=dt.UTC)
    end_dt = dt.datetime.combine(end, dt.time.max, tzinfo=dt.UTC)
    return start_dt, end_dt


def _msg_query(
    ctx: OrgContext, start: dt.datetime, end: dt.datetime, agent_id: uuid.UUID | None
) -> Select[Any]:
    stmt = select(Message).where(
        Message.organization_id == ctx.org.id,
        Message.created_at >= start,
        Message.created_at <= end,
    )
    if agent_id is not None:
        stmt = stmt.join(Conversation, Conversation.id == Message.conversation_id).where(
            Conversation.agent_id == agent_id
        )
    return stmt


def _conv_filter(ctx: OrgContext, start: dt.datetime, end: dt.datetime, agent_id: uuid.UUID | None) -> Any:
    conds = [
        Conversation.organization_id == ctx.org.id,
        Conversation.created_at >= start,
        Conversation.created_at <= end,
    ]
    if agent_id is not None:
        conds.append(Conversation.agent_id == agent_id)
    return conds


async def overview(
    session: AsyncSession,
    ctx: OrgContext,
    agent_id: uuid.UUID | None,
    from_date: dt.date | None,
    to_date: dt.date | None,
) -> schemas.Overview:
    rbac.require_permission(ctx.role, rbac.ANALYTICS_VIEW)
    start, end = _range(from_date, to_date)
    conv_conds = _conv_filter(ctx, start, end, agent_id)

    conversations = int(
        (await session.execute(select(func.count()).select_from(Conversation).where(*conv_conds))).scalar_one()
    )
    users = int(
        (
            await session.execute(
                select(func.count(distinct(Conversation.channel_user_id))).where(
                    *conv_conds, Conversation.channel_user_id.is_not(None)
                )
            )
        ).scalar_one()
    )
    msg_sub = _msg_query(ctx, start, end, agent_id).subquery()
    row = (
        await session.execute(
            select(
                func.count(),
                func.coalesce(func.sum(msg_sub.c.tokens_prompt), 0),
                func.coalesce(func.sum(msg_sub.c.tokens_completion), 0),
                func.coalesce(func.sum(msg_sub.c.cost_micros), 0),
            ).select_from(msg_sub)
        )
    ).one()
    messages, tok_p, tok_c, cost = int(row[0]), int(row[1]), int(row[2]), int(row[3])

    handoff_convs = int(
        (
            await session.execute(
                select(func.count(distinct(Handoff.conversation_id)))
                .select_from(Handoff)
                .join(Conversation, Conversation.id == Handoff.conversation_id)
                .where(*conv_conds, Handoff.organization_id == ctx.org.id)
            )
        ).scalar_one()
    )
    handoff_rate = round(handoff_convs / conversations, 4) if conversations else 0.0
    return schemas.Overview(
        conversations=conversations,
        messages=messages,
        users=users,
        tokens_prompt=tok_p,
        tokens_completion=tok_c,
        cost_micros=cost,
        handoff_rate=handoff_rate,
        resolution_rate=round(1 - handoff_rate, 4),
    )


async def usage(
    session: AsyncSession,
    ctx: OrgContext,
    agent_id: uuid.UUID | None,
    from_date: dt.date | None,
    to_date: dt.date | None,
    group_by: str,
) -> list[schemas.UsageBucket]:
    rbac.require_permission(ctx.role, rbac.ANALYTICS_VIEW)
    start, end = _range(from_date, to_date)
    sub = _msg_query(ctx, start, end, agent_id).where(Message.role == "assistant").subquery()

    key_col: Any
    if group_by == "provider":
        key_col = func.coalesce(sub.c.provider, "unknown")
    elif group_by == "model":
        key_col = func.coalesce(sub.c.model, "unknown")
    else:
        key_col = cast(sub.c.created_at, Date)

    stmt = (
        select(
            key_col.label("key"),
            func.coalesce(func.sum(sub.c.tokens_prompt), 0),
            func.coalesce(func.sum(sub.c.tokens_completion), 0),
            func.count(),
            func.coalesce(func.sum(sub.c.cost_micros), 0),
        )
        .group_by(key_col)
        .order_by(key_col)
    )
    rows = (await session.execute(stmt)).all()
    return [
        schemas.UsageBucket(
            key=str(r[0]),
            tokens_prompt=int(r[1]),
            tokens_completion=int(r[2]),
            requests=int(r[3]),
            cost_micros=int(r[4]),
        )
        for r in rows
    ]


async def latency(
    session: AsyncSession,
    ctx: OrgContext,
    agent_id: uuid.UUID | None,
    from_date: dt.date | None,
    to_date: dt.date | None,
) -> schemas.LatencyStats:
    rbac.require_permission(ctx.role, rbac.ANALYTICS_VIEW)
    start, end = _range(from_date, to_date)
    sub = (
        _msg_query(ctx, start, end, agent_id)
        .where(Message.role == "assistant", Message.latency_ms.is_not(None))
        .subquery()
    )
    row = (
        await session.execute(
            select(
                func.count(),
                func.coalesce(func.avg(sub.c.latency_ms), 0),
                func.percentile_cont(0.5).within_group(sub.c.latency_ms.asc()),
                func.percentile_cont(0.95).within_group(sub.c.latency_ms.asc()),
            ).select_from(sub)
        )
    ).one()
    return schemas.LatencyStats(
        count=int(row[0]),
        avg_ms=round(float(row[1]), 1),
        p50_ms=int(row[2] or 0),
        p95_ms=int(row[3] or 0),
    )


async def top_questions(
    session: AsyncSession,
    ctx: OrgContext,
    agent_id: uuid.UUID | None,
    from_date: dt.date | None,
    to_date: dt.date | None,
    limit: int = 10,
) -> list[schemas.QuestionCount]:
    rbac.require_permission(ctx.role, rbac.ANALYTICS_VIEW)
    start, end = _range(from_date, to_date)
    sub = _msg_query(ctx, start, end, agent_id).where(Message.role == "user").subquery()
    stmt = (
        select(sub.c.content, func.count().label("n"))
        .where(sub.c.content.is_not(None))
        .group_by(sub.c.content)
        .order_by(func.count().desc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    return [schemas.QuestionCount(question=str(r[0])[:200], count=int(r[1])) for r in rows]


async def unanswered(
    session: AsyncSession,
    ctx: OrgContext,
    agent_id: uuid.UUID | None,
    from_date: dt.date | None,
    to_date: dt.date | None,
    limit: int = 10,
) -> list[schemas.QuestionCount]:
    """Heuristic: user questions in conversations that escalated to a human (a handoff record)."""
    rbac.require_permission(ctx.role, rbac.ANALYTICS_VIEW)
    start, end = _range(from_date, to_date)
    handoff_convs = select(Handoff.conversation_id).where(Handoff.organization_id == ctx.org.id)
    sub = (
        _msg_query(ctx, start, end, agent_id)
        .where(Message.role == "user", Message.conversation_id.in_(handoff_convs))
        .subquery()
    )
    stmt = (
        select(sub.c.content, func.count().label("n"))
        .where(sub.c.content.is_not(None))
        .group_by(sub.c.content)
        .order_by(func.count().desc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    return [schemas.QuestionCount(question=str(r[0])[:200], count=int(r[1])) for r in rows]


async def export_csv(
    session: AsyncSession,
    ctx: OrgContext,
    kind: str,
    agent_id: uuid.UUID | None,
    from_date: dt.date | None,
    to_date: dt.date | None,
) -> str:
    rbac.require_permission(ctx.role, rbac.ANALYTICS_VIEW)
    start, end = _range(from_date, to_date)
    lines: list[str] = []
    if kind == "conversations":
        conds = _conv_filter(ctx, start, end, agent_id)
        stmt = select(Conversation).where(*conds).order_by(Conversation.created_at.desc())
        convs = (await session.execute(stmt)).scalars().all()
        lines.append("id,channel,status,title,created_at")
        for c in convs:
            title = (c.title or "").replace(",", " ").replace("\n", " ")
            lines.append(f"{c.id},{c.channel},{c.status},{title},{c.created_at.isoformat()}")
    else:  # usage — per day/provider/model
        sub = _msg_query(ctx, start, end, agent_id).where(Message.role == "assistant").subquery()
        stmt = (
            select(
                cast(sub.c.created_at, Date),
                func.coalesce(sub.c.provider, "unknown"),
                func.coalesce(sub.c.model, "unknown"),
                func.coalesce(func.sum(sub.c.tokens_prompt), 0),
                func.coalesce(func.sum(sub.c.tokens_completion), 0),
                func.count(),
                func.coalesce(func.sum(sub.c.cost_micros), 0),
            )
            .group_by(cast(sub.c.created_at, Date), sub.c.provider, sub.c.model)
            .order_by(cast(sub.c.created_at, Date))
        )
        rows = (await session.execute(stmt)).all()
        lines.append("date,provider,model,tokens_prompt,tokens_completion,requests,cost_micros")
        for r in rows:
            lines.append(f"{r[0]},{r[1]},{r[2]},{int(r[3])},{int(r[4])},{int(r[5])},{int(r[6])}")
    return "\n".join(lines) + "\n"
