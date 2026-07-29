"""Canned response CRUD, org-scoped."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import rbac
from app.core.errors import AppError
from app.models import CannedResponse
from app.modules.canned_responses import schemas
from app.modules.orgs.deps import OrgContext


def _out(row: CannedResponse) -> schemas.CannedResponseOut:
    return schemas.CannedResponseOut(
        id=row.id,
        shortcut=row.shortcut,
        content=row.content,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def _get(session: AsyncSession, ctx: OrgContext, cr_id: uuid.UUID) -> CannedResponse:
    row = await session.get(CannedResponse, cr_id)
    if row is None or row.organization_id != ctx.org.id:
        raise AppError("canned_responses.not_found", "Canned response not found.", 404)
    return row


async def _reject_duplicate(
    session: AsyncSession, ctx: OrgContext, shortcut: str, exclude: uuid.UUID | None = None
) -> None:
    stmt = select(CannedResponse.id).where(
        CannedResponse.organization_id == ctx.org.id, CannedResponse.shortcut == shortcut
    )
    if exclude is not None:
        stmt = stmt.where(CannedResponse.id != exclude)
    if (await session.execute(stmt)).first() is not None:
        raise AppError(
            "canned_responses.duplicate_shortcut",
            f"'/{shortcut}' is already used by another canned response.",
            409,
        )


async def list_canned_responses(
    session: AsyncSession, ctx: OrgContext, query: str | None = None
) -> list[schemas.CannedResponseOut]:
    """Every operator needs these to reply, so reading them is a base `READ` capability."""
    rbac.require_permission(ctx.role, rbac.READ)
    stmt = (
        select(CannedResponse)
        .where(CannedResponse.organization_id == ctx.org.id)
        .order_by(CannedResponse.shortcut.asc())
    )
    if query:
        like = f"%{query.strip().lstrip('/').lower()}%"
        stmt = stmt.where(CannedResponse.shortcut.ilike(like))
    return [_out(r) for r in (await session.execute(stmt)).scalars().all()]


async def create_canned_response(
    session: AsyncSession, ctx: OrgContext, data: schemas.CreateCannedResponseRequest
) -> schemas.CannedResponseOut:
    rbac.require_permission(ctx.role, rbac.INBOX_HANDLE)
    await _reject_duplicate(session, ctx, data.shortcut)
    row = CannedResponse(
        organization_id=ctx.org.id,
        shortcut=data.shortcut,
        content=data.content,
        created_by=ctx.user.id,
    )
    session.add(row)
    try:
        await session.flush()
    except IntegrityError as exc:  # lost a race against a concurrent create
        raise AppError(
            "canned_responses.duplicate_shortcut",
            f"'/{data.shortcut}' is already used by another canned response.",
            409,
        ) from exc
    return _out(row)


async def update_canned_response(
    session: AsyncSession,
    ctx: OrgContext,
    cr_id: uuid.UUID,
    data: schemas.UpdateCannedResponseRequest,
) -> schemas.CannedResponseOut:
    rbac.require_permission(ctx.role, rbac.INBOX_HANDLE)
    row = await _get(session, ctx, cr_id)
    if data.shortcut is not None and data.shortcut != row.shortcut:
        await _reject_duplicate(session, ctx, data.shortcut, exclude=row.id)
        row.shortcut = data.shortcut
    if data.content is not None:
        row.content = data.content
    await session.flush()
    return _out(row)


async def delete_canned_response(session: AsyncSession, ctx: OrgContext, cr_id: uuid.UUID) -> None:
    rbac.require_permission(ctx.role, rbac.INBOX_HANDLE)
    row = await _get(session, ctx, cr_id)
    await session.delete(row)
