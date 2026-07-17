"""Org resolution dependencies + membership enforcement."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.session import get_session
from app.models import Membership, Organization, User
from app.modules.auth.deps import get_current_user


@dataclass(slots=True)
class OrgContext:
    org: Organization
    membership: Membership
    user: User

    @property
    def role(self) -> str:
        return self.membership.role


async def _load_context(session: AsyncSession, user: User, org_id: uuid.UUID) -> OrgContext:
    org = await session.get(Organization, org_id)
    if org is None or org.deleted_at is not None:
        raise AppError("org.not_found", "Organization not found.", 404)
    stmt = select(Membership).where(
        Membership.organization_id == org_id,
        Membership.user_id == user.id,
        Membership.status == "active",
    )
    membership = (await session.execute(stmt)).scalar_one_or_none()
    if membership is None:
        raise AppError("org.forbidden", "You are not a member of this organization.", 403)
    return OrgContext(org=org, membership=membership, user=user)


async def org_context(
    org_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> OrgContext:
    """Resolve org + membership from the path `{org_id}` (for /v1/orgs/{org_id}/...)."""
    return await _load_context(session, user, org_id)


async def current_org(
    x_org_id: uuid.UUID | None = Header(default=None, alias="X-Org-Id"),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> OrgContext:
    """Resolve the active org from the `X-Org-Id` header (for org-scoped resource routes)."""
    if x_org_id is None:
        raise AppError("org.missing_header", "X-Org-Id header is required.", 400)
    return await _load_context(session, user, x_org_id)
