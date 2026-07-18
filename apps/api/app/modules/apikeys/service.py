"""API key issuance, listing, revocation, and resolution for key-based auth."""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import secrets
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import rbac
from app.core.audit import write_audit
from app.core.errors import AppError
from app.models import ApiKey
from app.modules.apikeys import schemas
from app.modules.orgs.deps import OrgContext

_PREFIX_LEN = 12  # "bf_" + 9 chars, stored for O(1) lookup


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _generate() -> tuple[str, str, str]:
    raw = "bf_" + secrets.token_urlsafe(32)
    return raw, raw[:_PREFIX_LEN], _hash(raw)


def _out(key: ApiKey) -> schemas.ApiKeyOut:
    return schemas.ApiKeyOut(
        id=key.id,
        name=key.name,
        key_prefix=key.key_prefix,
        scopes=key.scopes,
        last_used_at=key.last_used_at,
        expires_at=key.expires_at,
        revoked_at=key.revoked_at,
        created_at=key.created_at,
    )


async def create_api_key(
    session: AsyncSession, ctx: OrgContext, data: schemas.CreateApiKeyRequest
) -> schemas.ApiKeyCreated:
    rbac.require_permission(ctx.role, rbac.TOOLS_MANAGE)
    raw, prefix, key_hash = _generate()
    key = ApiKey(
        organization_id=ctx.org.id,
        name=data.name,
        key_prefix=prefix,
        key_hash=key_hash,
        scopes=data.scopes,
        expires_at=data.expires_at,
        created_by=ctx.user.id,
    )
    session.add(key)
    await session.flush()
    await write_audit(session, ctx.org.id, ctx.user.id, "apikey.created", target_type="api_key", target_id=str(key.id))
    return schemas.ApiKeyCreated(**_out(key).model_dump(), key=raw)


async def list_api_keys(session: AsyncSession, ctx: OrgContext) -> list[schemas.ApiKeyOut]:
    rbac.require_permission(ctx.role, rbac.READ)
    stmt = select(ApiKey).where(ApiKey.organization_id == ctx.org.id).order_by(ApiKey.created_at.desc())
    return [_out(k) for k in (await session.execute(stmt)).scalars().all()]


async def _get(session: AsyncSession, ctx: OrgContext, key_id: uuid.UUID) -> ApiKey:
    key = await session.get(ApiKey, key_id)
    if key is None or key.organization_id != ctx.org.id:
        raise AppError("apikeys.not_found", "API key not found.", 404)
    return key


async def revoke_api_key(session: AsyncSession, ctx: OrgContext, key_id: uuid.UUID) -> schemas.ApiKeyOut:
    rbac.require_permission(ctx.role, rbac.TOOLS_MANAGE)
    key = await _get(session, ctx, key_id)
    key.revoked_at = dt.datetime.now(tz=dt.UTC)
    await write_audit(session, ctx.org.id, ctx.user.id, "apikey.revoked", target_type="api_key", target_id=str(key.id))
    return _out(key)


async def delete_api_key(session: AsyncSession, ctx: OrgContext, key_id: uuid.UUID) -> None:
    rbac.require_permission(ctx.role, rbac.TOOLS_MANAGE)
    key = await _get(session, ctx, key_id)
    await write_audit(session, ctx.org.id, ctx.user.id, "apikey.deleted", target_type="api_key", target_id=str(key.id))
    await session.delete(key)


async def resolve_api_key(session: AsyncSession, raw_key: str) -> ApiKey | None:
    """Verify a presented key: prefix lookup → constant-time hash check → validity. Updates last_used_at."""
    if not raw_key.startswith("bf_"):
        return None
    prefix = raw_key[:_PREFIX_LEN]
    stmt = select(ApiKey).where(ApiKey.key_prefix == prefix)
    candidates = (await session.execute(stmt)).scalars().all()
    presented = _hash(raw_key)
    now = dt.datetime.now(tz=dt.UTC)
    for key in candidates:
        if not hmac.compare_digest(key.key_hash, presented):
            continue
        if key.revoked_at is not None:
            return None
        if key.expires_at is not None and key.expires_at < now:
            return None
        key.last_used_at = now
        return key
    return None
