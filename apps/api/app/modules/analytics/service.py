"""Analytics aggregation — computed live from messages/conversations/handoffs (org-scoped)."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import Date, String, cast, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.selectable import Select

from app.core import rbac
from app.models import Channel, Conversation, Handoff, Message
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
    ctx: OrgContext,
    start: dt.datetime,
    end: dt.datetime,
    agent_id: uuid.UUID | None,
    channel: str | None = None,
    *,
    include_channel: bool = False,
) -> Select[Any]:
    """Messages in range. Joins `conversations` when the caller needs the agent or the
    channel — filtering by one, or selecting the channel as a grouping key."""
    cols: list[Any] = [Message]
    if include_channel:
        cols.append(Conversation.channel.label("channel"))
    stmt = select(*cols).where(
        Message.organization_id == ctx.org.id,
        Message.created_at >= start,
        Message.created_at <= end,
    )
    if include_channel or agent_id is not None or channel is not None:
        stmt = stmt.join(Conversation, Conversation.id == Message.conversation_id)
    if agent_id is not None:
        stmt = stmt.where(Conversation.agent_id == agent_id)
    if channel is not None:
        stmt = stmt.where(Conversation.channel == channel)
    return stmt


def _conv_filter(
    ctx: OrgContext,
    start: dt.datetime,
    end: dt.datetime,
    agent_id: uuid.UUID | None,
    channel: str | None = None,
) -> Any:
    conds = [
        Conversation.organization_id == ctx.org.id,
        Conversation.created_at >= start,
        Conversation.created_at <= end,
    ]
    if agent_id is not None:
        conds.append(Conversation.agent_id == agent_id)
    if channel is not None:
        conds.append(Conversation.channel == channel)
    return conds


async def _connected_channels(
    session: AsyncSession, ctx: OrgContext, agent_id: uuid.UUID | None
) -> set[str]:
    """Channel types this org can currently receive on.

    `widget` is always in the set: every agent carries the embeddable web chat inherently,
    so it has no `channels` row to enable (same rule the inbox tab bar follows). The rest
    must have an enabled row — a channel that was connected and then switched off stops
    being something the operator expects traffic on.
    """
    stmt = select(distinct(Channel.type)).where(
        Channel.organization_id == ctx.org.id, Channel.enabled.is_(True)
    )
    if agent_id is not None:
        stmt = stmt.where(Channel.agent_id == agent_id)
    types = {str(t) for t in (await session.execute(stmt)).scalars().all()}
    return types | {"widget"}


def _rates(handoffs: int, conversations: int) -> tuple[float, float]:
    """Handoff/resolution rates, guarding the zero-conversation case (no divide-by-zero)."""
    if not conversations:
        return 0.0, 0.0
    handoff_rate = round(handoffs / conversations, 4)
    return handoff_rate, round(1 - handoff_rate, 4)


async def _by_channel(
    session: AsyncSession,
    ctx: OrgContext,
    start: dt.datetime,
    end: dt.datetime,
    agent_id: uuid.UUID | None,
    channel: str | None,
) -> list[schemas.ChannelBucket]:
    """Per-channel slice of the overview metrics.

    Three grouped queries (conversations, messages, handoffs) merged in Python, mirroring
    the separate-scalar-queries style `overview()` already uses. Crucially the channel set
    is the *union* of what has traffic and what's connected — a plain `GROUP BY channel`
    over conversations would silently drop a channel that's live but hasn't been messaged
    yet, which is exactly the case this breakdown exists to make visible.
    """
    conv_conds = _conv_filter(ctx, start, end, agent_id, channel)

    conv_counts = {
        str(r[0]): int(r[1])
        for r in (
            await session.execute(
                select(Conversation.channel, func.count()).where(*conv_conds).group_by(Conversation.channel)
            )
        ).all()
    }

    msg_stmt = (
        select(
            Conversation.channel,
            func.count(),
            func.coalesce(func.sum(Message.tokens_prompt), 0),
            func.coalesce(func.sum(Message.tokens_completion), 0),
            func.coalesce(func.sum(Message.cost_micros), 0),
        )
        .select_from(Message)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(
            Message.organization_id == ctx.org.id,
            Message.created_at >= start,
            Message.created_at <= end,
        )
        .group_by(Conversation.channel)
    )
    if agent_id is not None:
        msg_stmt = msg_stmt.where(Conversation.agent_id == agent_id)
    if channel is not None:
        msg_stmt = msg_stmt.where(Conversation.channel == channel)
    msg_rows = {
        str(r[0]): (int(r[1]), int(r[2]), int(r[3]), int(r[4]))
        for r in (await session.execute(msg_stmt)).all()
    }

    handoff_counts = {
        str(r[0]): int(r[1])
        for r in (
            await session.execute(
                select(Conversation.channel, func.count(distinct(Handoff.conversation_id)))
                .select_from(Handoff)
                .join(Conversation, Conversation.id == Handoff.conversation_id)
                .where(*conv_conds, Handoff.organization_id == ctx.org.id)
                .group_by(Conversation.channel)
            )
        ).all()
    }

    connected = await _connected_channels(session, ctx, agent_id)
    if channel is not None:
        connected = {channel} if channel in connected else set()
    keys = sorted(set(conv_counts) | set(msg_rows) | connected)

    buckets: list[schemas.ChannelBucket] = []
    for key in keys:
        conversations = conv_counts.get(key, 0)
        messages, tok_p, tok_c, cost = msg_rows.get(key, (0, 0, 0, 0))
        handoff_rate, resolution_rate = _rates(handoff_counts.get(key, 0), conversations)
        buckets.append(
            schemas.ChannelBucket(
                channel=key,
                conversations=conversations,
                messages=messages,
                tokens_prompt=tok_p,
                tokens_completion=tok_c,
                cost_micros=cost,
                handoff_rate=handoff_rate,
                resolution_rate=resolution_rate,
            )
        )
    # Busiest first; ties (notably the zero rows) fall back to name for a stable order.
    buckets.sort(key=lambda b: (-b.conversations, b.channel))
    return buckets


async def overview(
    session: AsyncSession,
    ctx: OrgContext,
    agent_id: uuid.UUID | None,
    from_date: dt.date | None,
    to_date: dt.date | None,
    channel: str | None = None,
) -> schemas.Overview:
    rbac.require_permission(ctx.role, rbac.ANALYTICS_VIEW)
    start, end = _range(from_date, to_date)
    conv_conds = _conv_filter(ctx, start, end, agent_id, channel)

    conversations = int(
        (await session.execute(select(func.count()).select_from(Conversation).where(*conv_conds))).scalar_one()
    )
    # Distinct end users. Only channel/widget conversations carry a `channel_user_id`;
    # dashboard and API conversations have none, and counting only the former reported
    # "0 users" next to N conversations for an org whose traffic is all dashboard. An
    # untracked conversation is one person, so it falls back to the conversation id.
    users = int(
        (
            await session.execute(
                select(
                    func.count(
                        distinct(
                            func.coalesce(
                                Conversation.channel_user_id, cast(Conversation.id, String)
                            )
                        )
                    )
                ).where(*conv_conds)
            )
        ).scalar_one()
    )
    msg_sub = _msg_query(ctx, start, end, agent_id, channel).subquery()
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
        by_channel=await _by_channel(session, ctx, start, end, agent_id, channel),
    )


async def usage(
    session: AsyncSession,
    ctx: OrgContext,
    agent_id: uuid.UUID | None,
    from_date: dt.date | None,
    to_date: dt.date | None,
    group_by: str,
    channel: str | None = None,
) -> list[schemas.UsageBucket]:
    rbac.require_permission(ctx.role, rbac.ANALYTICS_VIEW)
    start, end = _range(from_date, to_date)
    by_channel = group_by == "channel"
    sub = (
        _msg_query(ctx, start, end, agent_id, channel, include_channel=by_channel)
        .where(Message.role == "assistant")
        .subquery()
    )

    key_col: Any
    if group_by == "provider":
        key_col = func.coalesce(sub.c.provider, "unknown")
    elif group_by == "model":
        key_col = func.coalesce(sub.c.model, "unknown")
    elif by_channel:
        key_col = func.coalesce(sub.c.channel, "unknown")
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
    buckets = [
        schemas.UsageBucket(
            key=str(r[0]),
            tokens_prompt=int(r[1]),
            tokens_completion=int(r[2]),
            requests=int(r[3]),
            cost_micros=int(r[4]),
        )
        for r in rows
    ]
    if by_channel:
        # Unlike day/provider/model, a channel exists independently of its traffic: a
        # connected channel nobody has messaged yet is a real, reportable zero.
        seen = {b.key for b in buckets}
        connected = await _connected_channels(session, ctx, agent_id)
        if channel is not None:
            connected &= {channel}
        buckets.extend(
            schemas.UsageBucket(key=c, tokens_prompt=0, tokens_completion=0, requests=0, cost_micros=0)
            for c in sorted(connected - seen)
        )
        buckets.sort(key=lambda b: b.key)
    return buckets


async def latency(
    session: AsyncSession,
    ctx: OrgContext,
    agent_id: uuid.UUID | None,
    from_date: dt.date | None,
    to_date: dt.date | None,
    channel: str | None = None,
) -> schemas.LatencyStats:
    rbac.require_permission(ctx.role, rbac.ANALYTICS_VIEW)
    start, end = _range(from_date, to_date)
    sub = (
        _msg_query(ctx, start, end, agent_id, channel)
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
    channel: str | None = None,
) -> list[schemas.QuestionCount]:
    rbac.require_permission(ctx.role, rbac.ANALYTICS_VIEW)
    start, end = _range(from_date, to_date)
    sub = _msg_query(ctx, start, end, agent_id, channel).where(Message.role == "user").subquery()
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
    channel: str | None = None,
) -> list[schemas.QuestionCount]:
    """Heuristic: user questions in conversations that escalated to a human (a handoff record)."""
    rbac.require_permission(ctx.role, rbac.ANALYTICS_VIEW)
    start, end = _range(from_date, to_date)
    handoff_convs = select(Handoff.conversation_id).where(Handoff.organization_id == ctx.org.id)
    sub = (
        _msg_query(ctx, start, end, agent_id, channel)
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
    channel: str | None = None,
) -> str:
    rbac.require_permission(ctx.role, rbac.ANALYTICS_VIEW)
    start, end = _range(from_date, to_date)
    lines: list[str] = []
    if kind == "conversations":
        conds = _conv_filter(ctx, start, end, agent_id, channel)
        stmt = select(Conversation).where(*conds).order_by(Conversation.created_at.desc())
        convs = (await session.execute(stmt)).scalars().all()
        lines.append("id,channel,status,title,created_at")
        for c in convs:
            title = (c.title or "").replace(",", " ").replace("\n", " ")
            lines.append(f"{c.id},{c.channel},{c.status},{title},{c.created_at.isoformat()}")
    elif kind == "channels":
        # Same buckets the Dashboard/Analytics breakdown renders, zero rows included.
        buckets = await _by_channel(session, ctx, start, end, agent_id, channel)
        lines.append(
            "channel,conversations,messages,tokens_prompt,tokens_completion,cost_micros,"
            "handoff_rate,resolution_rate"
        )
        for b in buckets:
            lines.append(
                f"{b.channel},{b.conversations},{b.messages},{b.tokens_prompt},"
                f"{b.tokens_completion},{b.cost_micros},{b.handoff_rate},{b.resolution_rate}"
            )
    else:  # usage — per day/provider/model
        sub = _msg_query(ctx, start, end, agent_id, channel).where(Message.role == "assistant").subquery()
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
