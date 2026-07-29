"""Macro CRUD and execution.

Execution deliberately reuses the same inbox service functions the manual buttons call —
one implementation of "reply", "tag", "assign", "close", so a macro can never drift from
what those do (RBAC checks, webhook events, realtime publishes and all).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import rbac
from app.core.errors import AppError
from app.core.logging import get_logger
from app.models import CannedResponse, Macro, Membership
from app.modules.inbox import service as inbox_service
from app.modules.macros import schemas
from app.modules.orgs.deps import OrgContext

log = get_logger("macros")


def _out(row: Macro) -> schemas.MacroOut:
    return schemas.MacroOut(
        id=row.id,
        name=row.name,
        actions=[schemas.MacroAction(**a) for a in row.actions],
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def _get(session: AsyncSession, ctx: OrgContext, macro_id: uuid.UUID) -> Macro:
    row = await session.get(Macro, macro_id)
    if row is None or row.organization_id != ctx.org.id:
        raise AppError("macros.not_found", "Macro not found.", 404)
    return row


# ── CRUD ─────────────────────────────────────────────────────────────────────────
async def list_macros(session: AsyncSession, ctx: OrgContext) -> list[schemas.MacroOut]:
    rbac.require_permission(ctx.role, rbac.READ)
    stmt = select(Macro).where(Macro.organization_id == ctx.org.id).order_by(Macro.name.asc())
    return [_out(r) for r in (await session.execute(stmt)).scalars().all()]


async def create_macro(
    session: AsyncSession, ctx: OrgContext, data: schemas.CreateMacroRequest
) -> schemas.MacroOut:
    rbac.require_permission(ctx.role, rbac.INBOX_HANDLE)
    row = Macro(
        organization_id=ctx.org.id,
        name=data.name,
        actions=[a.model_dump() for a in data.actions],
        created_by=ctx.user.id,
    )
    session.add(row)
    await session.flush()
    return _out(row)


async def update_macro(
    session: AsyncSession, ctx: OrgContext, macro_id: uuid.UUID, data: schemas.UpdateMacroRequest
) -> schemas.MacroOut:
    rbac.require_permission(ctx.role, rbac.INBOX_HANDLE)
    row = await _get(session, ctx, macro_id)
    if data.name is not None:
        row.name = data.name
    if data.actions is not None:
        row.actions = [a.model_dump() for a in data.actions]
    await session.flush()
    return _out(row)


async def delete_macro(session: AsyncSession, ctx: OrgContext, macro_id: uuid.UUID) -> None:
    rbac.require_permission(ctx.role, rbac.INBOX_HANDLE)
    row = await _get(session, ctx, macro_id)
    await session.delete(row)


# ── Execution ────────────────────────────────────────────────────────────────────
async def _resolve_reply_text(
    session: AsyncSession, ctx: OrgContext, params: dict[str, Any]
) -> str:
    canned_id = params.get("canned_response_id")
    if canned_id:
        row = await session.get(CannedResponse, uuid.UUID(str(canned_id)))
        if row is None or row.organization_id != ctx.org.id:
            raise AppError(
                "macros.canned_response_missing",
                "This macro replies with a canned response that no longer exists.",
                400,
            )
        return row.content
    text = str(params.get("text") or "").strip()
    if not text:
        raise AppError("macros.invalid_action", "A reply action has no text.", 400)
    return text


async def _preflight(session: AsyncSession, ctx: OrgContext, macro: Macro) -> list[str]:
    """Validate every step *before* running any of them.

    A DB rollback can undo a tag; it cannot un-send a WhatsApp message. So anything that
    could fail — a deleted canned response, a teammate who has left the org — is caught
    while the conversation is still untouched.
    """
    resolved: list[str] = []
    for raw in macro.actions:
        action = schemas.MacroAction(**raw)
        if action.type == "reply":
            resolved.append(await _resolve_reply_text(session, ctx, action.params))
        elif action.type == "assign":
            user_id = uuid.UUID(str(action.params["user_id"]))
            member = (
                await session.execute(
                    select(Membership.id).where(
                        Membership.organization_id == ctx.org.id, Membership.user_id == user_id
                    )
                )
            ).first()
            if member is None:
                raise AppError(
                    "macros.assignee_not_a_member",
                    "This macro assigns to someone who is no longer in this organization.",
                    400,
                )
            resolved.append("")
        else:
            resolved.append("")
    return resolved


async def run_macro(
    session: AsyncSession, ctx: OrgContext, cid: uuid.UUID, macro_id: uuid.UUID
) -> schemas.MacroRunResult:
    """Run every action in order, or none of them.

    Wrapped in a SAVEPOINT so a failure half-way can't leave a conversation tagged but
    un-replied — partial application is confusing and hard to undo by hand.
    """
    rbac.require_permission(ctx.role, rbac.INBOX_HANDLE)
    macro = await _get(session, ctx, macro_id)
    if not macro.actions:
        raise AppError("macros.empty", "This macro has no actions.", 400)

    # Raises before anything is applied.
    resolved = await _preflight(session, ctx, macro)

    applied: list[str] = []
    async with session.begin_nested():
        for raw, reply_text in zip(macro.actions, resolved, strict=True):
            action = schemas.MacroAction(**raw)
            if action.type == "reply":
                await inbox_service.operator_reply(session, ctx, cid, reply_text)
            elif action.type == "add_tag":
                handoff = await inbox_service.get_tags(session, ctx, cid)
                tag = str(action.params["tag"]).strip()
                if tag not in handoff:
                    await inbox_service.set_tags(session, ctx, cid, [*handoff, tag])
            elif action.type == "assign":
                await inbox_service.assign(session, ctx, cid, uuid.UUID(str(action.params["user_id"])))
            elif action.type == "resolve":
                await inbox_service.close(session, ctx, cid)
            applied.append(action.type)

    log.info("macro_run", macro=str(macro_id), conversation=str(cid), actions=len(applied))
    return schemas.MacroRunResult(macro_id=macro_id, conversation_id=cid, applied=applied)
