"""Admin console service: cross-tenant aggregates (no org scoping — staff only)."""

from __future__ import annotations

import asyncio

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.probes import check_database, check_redis
from app.models import (
    Agent,
    Conversation,
    FeatureFlag,
    Membership,
    Message,
    Organization,
    UsageRecord,
    User,
)
from app.modules.admin import schemas


async def list_orgs(session: AsyncSession, limit: int = 100) -> list[schemas.OrgAdminOut]:
    members = (
        select(Membership.organization_id, func.count().label("n"))
        .where(Membership.status == "active")
        .group_by(Membership.organization_id)
        .subquery()
    )
    agents = (
        select(Agent.organization_id, func.count().label("n")).group_by(Agent.organization_id).subquery()
    )
    stmt = (
        select(
            Organization,
            func.coalesce(members.c.n, 0),
            func.coalesce(agents.c.n, 0),
        )
        .outerjoin(members, members.c.organization_id == Organization.id)
        .outerjoin(agents, agents.c.organization_id == Organization.id)
        .order_by(Organization.created_at.desc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    return [
        schemas.OrgAdminOut(
            id=org.id,
            name=org.name,
            slug=org.slug,
            members=int(m),
            agents=int(a),
            created_at=org.created_at,
            deleted=org.deleted_at is not None,
        )
        for org, m, a in rows
    ]


async def list_users(session: AsyncSession, limit: int = 100) -> list[schemas.UserAdminOut]:
    orgs = (
        select(Membership.user_id, func.count().label("n"))
        .where(Membership.status == "active")
        .group_by(Membership.user_id)
        .subquery()
    )
    stmt = (
        select(User, func.coalesce(orgs.c.n, 0))
        .outerjoin(orgs, orgs.c.user_id == User.id)
        .where(User.deleted_at.is_(None))
        .order_by(User.created_at.desc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    return [
        schemas.UserAdminOut(
            id=u.id,
            email=u.email,
            is_staff=u.is_staff,
            is_active=u.is_active,
            orgs=int(n),
            created_at=u.created_at,
        )
        for u, n in rows
    ]


async def platform_usage(session: AsyncSession) -> schemas.PlatformUsageOut:
    counts = await asyncio.gather(
        session.scalar(select(func.count()).select_from(Organization).where(Organization.deleted_at.is_(None))),
        session.scalar(select(func.count()).select_from(User).where(User.deleted_at.is_(None))),
        session.scalar(select(func.count()).select_from(Agent)),
        session.scalar(select(func.count()).select_from(Conversation)),
        session.scalar(select(func.count()).select_from(Message)),
    )
    totals = (
        await session.execute(
            select(
                func.coalesce(func.sum(UsageRecord.tokens_prompt), 0),
                func.coalesce(func.sum(UsageRecord.tokens_completion), 0),
                func.coalesce(func.sum(UsageRecord.cost_micros), 0),
            )
        )
    ).one()
    top_stmt = (
        select(
            Organization.id,
            Organization.name,
            func.coalesce(func.sum(UsageRecord.tokens_prompt), 0),
            func.coalesce(func.sum(UsageRecord.tokens_completion), 0),
            func.coalesce(func.sum(UsageRecord.requests), 0),
            func.coalesce(func.sum(UsageRecord.cost_micros), 0),
        )
        .join(UsageRecord, UsageRecord.organization_id == Organization.id)
        .group_by(Organization.id, Organization.name)
        .order_by(func.sum(UsageRecord.tokens_prompt).desc())
        .limit(10)
    )
    top = [
        schemas.OrgUsageRow(
            organization_id=oid,
            name=name,
            tokens_prompt=int(tp),
            tokens_completion=int(tc),
            requests=int(rq),
            cost_micros=int(cm),
        )
        for oid, name, tp, tc, rq, cm in (await session.execute(top_stmt)).all()
    ]
    return schemas.PlatformUsageOut(
        organizations=int(counts[0] or 0),
        users=int(counts[1] or 0),
        agents=int(counts[2] or 0),
        conversations=int(counts[3] or 0),
        messages=int(counts[4] or 0),
        tokens_prompt=int(totals[0]),
        tokens_completion=int(totals[1]),
        cost_micros=int(totals[2]),
        top_orgs=top,
    )


async def health(session: AsyncSession) -> schemas.HealthOut:
    db_ok, redis_ok, orgs, users, convos, msgs = await asyncio.gather(
        check_database(),
        check_redis(),
        session.scalar(select(func.count()).select_from(Organization).where(Organization.deleted_at.is_(None))),
        session.scalar(select(func.count()).select_from(User).where(User.deleted_at.is_(None))),
        session.scalar(select(func.count()).select_from(Conversation)),
        session.scalar(select(func.count()).select_from(Message)),
    )
    return schemas.HealthOut(
        database=db_ok,
        redis=redis_ok,
        organizations=int(orgs or 0),
        users=int(users or 0),
        conversations=int(convos or 0),
        messages=int(msgs or 0),
    )


async def list_flags(session: AsyncSession) -> list[schemas.FeatureFlagOut]:
    rows = (await session.execute(select(FeatureFlag).order_by(FeatureFlag.key))).scalars().all()
    return [
        schemas.FeatureFlagOut(key=f.key, enabled=f.enabled, description=f.description, updated_at=f.updated_at)
        for f in rows
    ]


async def upsert_flag(
    session: AsyncSession, key: str, data: schemas.FeatureFlagUpdate
) -> schemas.FeatureFlagOut:
    stmt = (
        pg_insert(FeatureFlag)
        .values(key=key, enabled=data.enabled, description=data.description)
        .on_conflict_do_update(
            index_elements=[FeatureFlag.key],
            set_={"enabled": data.enabled, "description": data.description},
        )
        .returning(FeatureFlag)
    )
    flag = (await session.execute(stmt)).scalar_one()
    return schemas.FeatureFlagOut(
        key=flag.key, enabled=flag.enabled, description=flag.description, updated_at=flag.updated_at
    )
