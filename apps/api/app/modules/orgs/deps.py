"""Org resolution dependencies + membership enforcement."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import rbac
from app.core.errors import AppError
from app.core.security import decode_access_token
from app.db.session import get_session
from app.models import Membership, Organization, User
from app.modules.auth.deps import get_current_user

_bearer = HTTPBearer(auto_error=False)


@dataclass(slots=True)
class OrgContext:
    org: Organization
    membership: Membership
    user: User
    via: str = "jwt"  # jwt | apikey
    scopes: list[str] = field(default_factory=list)
    role_override: str | None = None  # set for scoped API keys (least-privilege effective role)

    @property
    def role(self) -> str:
        """The effective role used for RBAC — a scoped API key downgrades this."""
        return self.role_override or self.membership.role

    @property
    def member_role(self) -> str:
        """The underlying membership role, ignoring any API-key scope downgrade."""
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
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_session),
) -> OrgContext:
    """Resolve the active org from `X-Org-Id` (JWT) or an API key (`X-API-Key` / `Bearer bf_…`).

    An API key authenticates programmatically: it resolves its own org and acts as its creating
    user (so `created_by`/audit/RBAC use the creator's membership role).
    """
    raw_key = x_api_key
    if raw_key is None and creds is not None and creds.credentials.startswith("bf_"):
        raw_key = creds.credentials

    if raw_key is not None:
        from app.modules.apikeys.service import resolve_api_key

        key = await resolve_api_key(session, raw_key)
        if key is None:
            raise AppError("auth.invalid_api_key", "Invalid or expired API key.", 401)
        if key.created_by is None:
            raise AppError("auth.orphan_api_key", "API key has no owner.", 401)
        user = await session.get(User, key.created_by)
        if user is None or not user.is_active or user.deleted_at is not None:
            raise AppError("auth.invalid_api_key", "API key owner is inactive.", 401)
        ctx = await _load_context(session, user, key.organization_id)
        ctx.via = "apikey"
        ctx.scopes = list(key.scopes)
        # Enforce scopes: the key acts with a role capped by its scope tier (least privilege).
        ctx.role_override = rbac.scope_effective_role(ctx.membership.role, ctx.scopes)
        return ctx

    # JWT path.
    if creds is None:
        raise AppError("auth.not_authenticated", "Authentication required", 401)
    claims = decode_access_token(creds.credentials)
    if claims is None:
        raise AppError("auth.invalid_token", "Invalid or expired token", 401)
    try:
        user_id = uuid.UUID(claims["sub"])
    except (KeyError, ValueError):
        raise AppError("auth.invalid_token", "Invalid or expired token", 401) from None
    user = await session.get(User, user_id)
    if user is None or not user.is_active or user.deleted_at is not None:
        raise AppError("auth.invalid_token", "Invalid or expired token", 401)
    if x_org_id is None:
        raise AppError("org.missing_header", "X-Org-Id header is required.", 400)
    return await _load_context(session, user, x_org_id)
