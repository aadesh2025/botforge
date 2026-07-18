"""Audit log routes under /v1/audit (docs/04 §Audit)."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import rbac
from app.db.session import get_session
from app.models import AuditLog
from app.modules.orgs.deps import OrgContext, current_org

router = APIRouter(prefix="/v1/audit", tags=["audit"])


class AuditEntryOut(BaseModel):
    id: uuid.UUID
    actor_user_id: uuid.UUID | None
    action: str
    target_type: str | None
    target_id: str | None
    meta: dict[str, Any]
    ip: str | None
    created_at: dt.datetime


@router.get("", response_model=list[AuditEntryOut])
async def list_audit(
    action: str | None = Query(default=None),
    actor_user_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
    ctx: OrgContext = Depends(current_org),
) -> list[AuditEntryOut]:
    rbac.require_permission(ctx.role, rbac.MEMBERS_MANAGE)  # admins + owners
    stmt = (
        select(AuditLog)
        .where(AuditLog.organization_id == ctx.org.id)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
    )
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if actor_user_id:
        stmt = stmt.where(AuditLog.actor_user_id == actor_user_id)
    rows = (await session.execute(stmt)).scalars().all()
    return [
        AuditEntryOut(
            id=r.id,
            actor_user_id=r.actor_user_id,
            action=r.action,
            target_type=r.target_type,
            target_id=r.target_id,
            meta=r.meta,
            ip=r.ip,
            created_at=r.created_at,
        )
        for r in rows
    ]
