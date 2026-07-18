"""Usage rollups: aggregate a day's assistant messages into usage_records + quotas.

Plain async functions (directly testable against the tx-rolled-back session); the Celery task
in ``app.worker.tasks`` wraps them with a committing session.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models import Conversation, Message, Quota, UsageRecord

log = get_logger("worker.rollup")

# Fraction of the token limit at which a `usage.threshold` event fires.
THRESHOLD_FRACTION = 0.8


async def rollup_usage(session: AsyncSession, org_id: uuid.UUID, target_date: dt.date) -> int:
    """Upsert usage_records for `org_id` on `target_date` from assistant messages. Returns rows written."""
    start = dt.datetime.combine(target_date, dt.time.min, tzinfo=dt.UTC)
    end = dt.datetime.combine(target_date, dt.time.max, tzinfo=dt.UTC)
    stmt = (
        select(
            Conversation.agent_id,
            func.coalesce(Message.provider, "unknown").label("provider"),
            func.coalesce(Message.model, "unknown").label("model"),
            func.coalesce(func.sum(Message.tokens_prompt), 0),
            func.coalesce(func.sum(Message.tokens_completion), 0),
            func.count(),
            func.coalesce(func.sum(Message.cost_micros), 0),
        )
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(
            Message.organization_id == org_id,
            Message.role == "assistant",
            Message.created_at >= start,
            Message.created_at <= end,
        )
        .group_by(Conversation.agent_id, "provider", "model")
    )
    rows = (await session.execute(stmt)).all()
    written = 0
    for agent_id, provider, model, tok_p, tok_c, requests, cost in rows:
        if agent_id is None:
            continue  # usage_records keys on agent_id (its unique index treats NULL as distinct)
        insert = (
            pg_insert(UsageRecord)
            .values(
                organization_id=org_id,
                agent_id=agent_id,
                date=target_date,
                provider=provider,
                model=model,
                tokens_prompt=int(tok_p),
                tokens_completion=int(tok_c),
                requests=int(requests),
                cost_micros=int(cost),
            )
            .on_conflict_do_update(
                index_elements=["organization_id", "agent_id", "date", "provider", "model"],
                set_={
                    "tokens_prompt": int(tok_p),
                    "tokens_completion": int(tok_c),
                    "requests": int(requests),
                    "cost_micros": int(cost),
                },
            )
        )
        await session.execute(insert)
        written += 1
    await session.flush()
    log.info("usage_rolled_up", org=str(org_id), date=str(target_date), rows=written)
    return written


async def refresh_quota(session: AsyncSession, org_id: uuid.UUID) -> tuple[int, bool]:
    """Recompute the org's month-to-date token usage into its Quota. Returns (tokens_used, threshold_crossed)."""
    today = dt.datetime.now(tz=dt.UTC).date()
    month_start = today.replace(day=1)
    totals = (
        await session.execute(
            select(
                func.coalesce(func.sum(UsageRecord.tokens_prompt + UsageRecord.tokens_completion), 0),
                func.coalesce(func.sum(UsageRecord.requests), 0),
            ).where(UsageRecord.organization_id == org_id, UsageRecord.date >= month_start)
        )
    ).one()
    tokens_used, requests_used = int(totals[0]), int(totals[1])

    quota = (
        await session.execute(select(Quota).where(Quota.organization_id == org_id).limit(1))
    ).scalar_one_or_none()
    if quota is None:
        quota = Quota(organization_id=org_id, period="month", token_limit=0, request_limit=0)
        session.add(quota)
    quota.tokens_used = tokens_used
    quota.requests_used = requests_used
    await session.flush()

    crossed = bool(quota.token_limit and tokens_used >= quota.token_limit * THRESHOLD_FRACTION)
    if crossed:
        log.warning("usage_threshold_crossed", org=str(org_id), used=tokens_used, limit=quota.token_limit)
    return tokens_used, crossed


async def rollup_org(session: AsyncSession, org_id: uuid.UUID, target_date: dt.date) -> dict[str, int]:
    """Roll up one org for a date and refresh its quota + fire a threshold event when crossed."""
    written = await rollup_usage(session, org_id, target_date)
    tokens_used, crossed = await refresh_quota(session, org_id)
    if crossed:
        # Emitted as a webhook event in Phase 15; import lazily to avoid a hard dependency.
        try:
            from app.webhooks.dispatch import emit_event

            await emit_event(
                session, org_id, "usage.threshold", {"tokens_used": tokens_used}
            )
        except Exception:  # webhooks optional
            pass
    return {"rows": written, "tokens_used": tokens_used}
