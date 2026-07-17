"""Provider-credential service (BYO keys), encrypted at rest."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import rbac
from app.core.crypto import decrypt, encrypt
from app.core.errors import AppError
from app.llm.base import ProviderError
from app.llm.registry import PROVIDER_CATALOG, build_chat_provider
from app.models import ProviderCredential
from app.modules.credentials import schemas
from app.modules.orgs.deps import OrgContext


def _mask(key: str) -> str:
    return "••••••••" + key[-4:] if len(key) > 4 else "••••"


def _out(cred: ProviderCredential) -> schemas.CredentialOut:
    masked = _mask(decrypt(cred.api_key_enc)) if cred.api_key_enc else "••••"
    return schemas.CredentialOut(
        id=cred.id,
        provider=cred.provider,
        label=cred.label,
        masked_key=masked,
        base_url=cred.base_url,
        is_default=cred.is_default,
        created_at=cred.created_at,
    )


async def list_credentials(session: AsyncSession, ctx: OrgContext) -> list[schemas.CredentialOut]:
    rbac.require_permission(ctx.role, rbac.TOOLS_MANAGE)
    stmt = (
        select(ProviderCredential)
        .where(ProviderCredential.organization_id == ctx.org.id, ProviderCredential.agent_id.is_(None))
        .order_by(ProviderCredential.created_at.desc())
    )
    return [_out(c) for c in (await session.execute(stmt)).scalars().all()]


async def _clear_default(session: AsyncSession, org_id: uuid.UUID, provider: str) -> None:
    stmt = select(ProviderCredential).where(
        ProviderCredential.organization_id == org_id,
        ProviderCredential.provider == provider,
        ProviderCredential.agent_id.is_(None),
        ProviderCredential.is_default.is_(True),
    )
    for c in (await session.execute(stmt)).scalars().all():
        c.is_default = False


async def create_credential(
    session: AsyncSession, ctx: OrgContext, data: schemas.CredentialCreate
) -> schemas.CredentialOut:
    rbac.require_permission(ctx.role, rbac.TOOLS_MANAGE)
    if data.is_default:
        await _clear_default(session, ctx.org.id, data.provider)
    cred = ProviderCredential(
        organization_id=ctx.org.id,
        provider=data.provider,
        label=data.label,
        api_key_enc=encrypt(data.api_key),
        base_url=data.base_url,
        is_default=data.is_default,
        created_by=ctx.user.id,
    )
    session.add(cred)
    await session.flush()
    return _out(cred)


async def _get_owned(session: AsyncSession, ctx: OrgContext, cred_id: uuid.UUID) -> ProviderCredential:
    cred = await session.get(ProviderCredential, cred_id)
    if cred is None or cred.organization_id != ctx.org.id:
        raise AppError("credentials.not_found", "Credential not found.", 404)
    return cred


async def update_credential(
    session: AsyncSession, ctx: OrgContext, cred_id: uuid.UUID, data: schemas.CredentialUpdate
) -> schemas.CredentialOut:
    rbac.require_permission(ctx.role, rbac.TOOLS_MANAGE)
    cred = await _get_owned(session, ctx, cred_id)
    if data.label is not None:
        cred.label = data.label
    if data.base_url is not None:
        cred.base_url = data.base_url
    if data.api_key is not None:
        cred.api_key_enc = encrypt(data.api_key)
    if data.is_default is not None:
        if data.is_default:
            await _clear_default(session, ctx.org.id, cred.provider)
        cred.is_default = data.is_default
    return _out(cred)


async def delete_credential(session: AsyncSession, ctx: OrgContext, cred_id: uuid.UUID) -> None:
    rbac.require_permission(ctx.role, rbac.TOOLS_MANAGE)
    cred = await _get_owned(session, ctx, cred_id)
    await session.delete(cred)


async def test_credential(
    session: AsyncSession, ctx: OrgContext, cred_id: uuid.UUID
) -> schemas.CredentialTestResult:
    rbac.require_permission(ctx.role, rbac.TOOLS_MANAGE)
    cred = await _get_owned(session, ctx, cred_id)
    api_key = decrypt(cred.api_key_enc) if cred.api_key_enc else None
    provider = build_chat_provider(cred.provider, api_key=api_key, base_url=cred.base_url)
    try:
        models = await provider.list_models()
        return schemas.CredentialTestResult(ok=True, models=[m.id for m in models])
    except ProviderError as exc:
        return schemas.CredentialTestResult(ok=False, error=str(exc))


def list_providers() -> list[schemas.ProviderInfo]:
    return [
        schemas.ProviderInfo(
            name=name,
            label=meta["label"],
            free=meta["free"],
            requires_key=meta["requires_key"],
            models=meta["models"],
        )
        for name, meta in PROVIDER_CATALOG.items()
    ]
