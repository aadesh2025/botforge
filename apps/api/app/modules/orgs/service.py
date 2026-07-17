"""Organizations, memberships, and invitations service."""

from __future__ import annotations

import datetime as dt
import re
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import rbac
from app.core.config import settings
from app.core.email import EmailMessage, get_email_backend
from app.core.errors import AppError
from app.core.security import generate_opaque_token, hash_token
from app.models import AuditLog, Invitation, Membership, Organization, User
from app.modules.orgs import schemas
from app.modules.orgs.deps import OrgContext

INVITE_TTL = dt.timedelta(days=7)


def _now() -> dt.datetime:
    return dt.datetime.now(tz=dt.UTC)


def _slug_base(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "org"


async def _unique_slug(session: AsyncSession, name: str) -> str:
    base = _slug_base(name)
    candidate = base
    n = 1
    while True:
        exists = (
            await session.execute(select(Organization.id).where(Organization.slug == candidate))
        ).scalar_one_or_none()
        if exists is None:
            return candidate
        n += 1
        candidate = f"{base}-{n}"


async def _write_audit(
    session: AsyncSession,
    org_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    action: str,
    *,
    target_type: str | None = None,
    target_id: str | None = None,
    meta: dict[str, Any] | None = None,
) -> None:
    session.add(
        AuditLog(
            organization_id=org_id,
            actor_user_id=actor_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            meta=meta or {},
        )
    )


def _org_out(org: Organization, role: str) -> schemas.OrgOut:
    return schemas.OrgOut(
        id=org.id,
        name=org.name,
        slug=org.slug,
        plan=org.plan,
        avatar_url=org.avatar_url,
        role=role,
        created_at=org.created_at,
        updated_at=org.updated_at,
    )


async def _active_membership(
    session: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID
) -> Membership | None:
    stmt = select(Membership).where(
        Membership.organization_id == org_id,
        Membership.user_id == user_id,
        Membership.status == "active",
    )
    return (await session.execute(stmt)).scalar_one_or_none()


# ── Org CRUD ──────────────────────────────────────────────────────────────────
async def create_org(session: AsyncSession, user: User, name: str) -> schemas.OrgOut:
    org = Organization(name=name, slug=await _unique_slug(session, name), created_by=user.id)
    session.add(org)
    await session.flush()
    session.add(Membership(organization_id=org.id, user_id=user.id, role="owner", status="active"))
    await _write_audit(session, org.id, user.id, "org.created", target_type="org", target_id=str(org.id))
    return _org_out(org, "owner")


async def list_orgs(session: AsyncSession, user: User) -> list[schemas.OrgOut]:
    stmt = (
        select(Organization, Membership.role)
        .join(Membership, Membership.organization_id == Organization.id)
        .where(
            Membership.user_id == user.id,
            Membership.status == "active",
            Organization.deleted_at.is_(None),
        )
        .order_by(Organization.created_at.asc())
    )
    return [_org_out(org, role) for org, role in (await session.execute(stmt)).all()]


async def update_org(session: AsyncSession, ctx: OrgContext, data: schemas.UpdateOrgRequest) -> schemas.OrgOut:
    rbac.require_permission(ctx.role, rbac.ORG_MANAGE)
    if data.name is not None:
        ctx.org.name = data.name
    if data.avatar_url is not None:
        ctx.org.avatar_url = data.avatar_url
    if data.settings is not None:
        ctx.org.settings = data.settings
    await _write_audit(session, ctx.org.id, ctx.user.id, "org.updated", target_type="org", target_id=str(ctx.org.id))
    return _org_out(ctx.org, ctx.role)


async def delete_org(session: AsyncSession, ctx: OrgContext) -> None:
    rbac.require_permission(ctx.role, rbac.ORG_MANAGE)
    ctx.org.deleted_at = _now()
    await _write_audit(session, ctx.org.id, ctx.user.id, "org.deleted", target_type="org", target_id=str(ctx.org.id))


# ── Members ───────────────────────────────────────────────────────────────────
async def list_members(session: AsyncSession, ctx: OrgContext) -> list[schemas.MemberOut]:
    stmt = (
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(Membership.organization_id == ctx.org.id, Membership.status == "active")
        .order_by(Membership.created_at.asc())
    )
    return [
        schemas.MemberOut(
            user_id=u.id,
            email=u.email,
            full_name=u.full_name,
            avatar_url=u.avatar_url,
            role=m.role,
            status=m.status,
            joined_at=m.created_at,
        )
        for m, u in (await session.execute(stmt)).all()
    ]


async def change_role(
    session: AsyncSession, ctx: OrgContext, target_user_id: uuid.UUID, role: str
) -> None:
    rbac.require_permission(ctx.role, rbac.MEMBERS_MANAGE)
    membership = await _active_membership(session, ctx.org.id, target_user_id)
    if membership is None:
        raise AppError("org.member_not_found", "Member not found.", 404)
    if membership.role == "owner":
        raise AppError("org.cannot_change_owner", "Use transfer ownership to change the owner.", 400)
    membership.role = role
    await _write_audit(
        session, ctx.org.id, ctx.user.id, "member.role_changed",
        target_type="user", target_id=str(target_user_id), meta={"role": role},
    )


async def remove_member(session: AsyncSession, ctx: OrgContext, target_user_id: uuid.UUID) -> None:
    rbac.require_permission(ctx.role, rbac.MEMBERS_MANAGE)
    membership = await _active_membership(session, ctx.org.id, target_user_id)
    if membership is None:
        raise AppError("org.member_not_found", "Member not found.", 404)
    if membership.role == "owner":
        raise AppError("org.cannot_remove_owner", "The owner cannot be removed.", 400)
    membership.status = "removed"
    await _write_audit(
        session, ctx.org.id, ctx.user.id, "member.removed", target_type="user", target_id=str(target_user_id)
    )


async def transfer_ownership(session: AsyncSession, ctx: OrgContext, target_user_id: uuid.UUID) -> None:
    rbac.require_permission(ctx.role, rbac.ORG_MANAGE)
    target = await _active_membership(session, ctx.org.id, target_user_id)
    if target is None:
        raise AppError("org.member_not_found", "Target member not found.", 404)
    ctx.membership.role = "admin"  # step down
    target.role = "owner"
    await _write_audit(
        session, ctx.org.id, ctx.user.id, "org.ownership_transferred",
        target_type="user", target_id=str(target_user_id),
    )


# ── Invitations ───────────────────────────────────────────────────────────────
async def create_invitation(
    session: AsyncSession, ctx: OrgContext, email: str, role: str
) -> schemas.InvitationOut:
    rbac.require_permission(ctx.role, rbac.MEMBERS_MANAGE)
    email = email.lower()
    existing_user = (
        await session.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()
    if existing_user is not None and await _active_membership(session, ctx.org.id, existing_user.id):
        raise AppError("org.already_member", "That person is already a member.", 409)

    raw = generate_opaque_token()
    invitation = Invitation(
        organization_id=ctx.org.id,
        email=email,
        role=role,
        token_hash=hash_token(raw),
        invited_by=ctx.user.id,
        expires_at=_now() + INVITE_TTL,
    )
    session.add(invitation)
    await session.flush()

    link = f"{settings.web_base_url}/invitations/accept?token={raw}"
    await get_email_backend().send(
        EmailMessage(
            to=email,
            subject=f"You're invited to {ctx.org.name}",
            body=f"Join {ctx.org.name} as {role}: {link}\nToken: {raw}",
        )
    )
    await _write_audit(
        session, ctx.org.id, ctx.user.id, "invitation.created",
        target_type="invitation", target_id=str(invitation.id), meta={"email": email, "role": role},
    )
    return schemas.InvitationOut(
        id=invitation.id,
        email=invitation.email,
        role=invitation.role,
        expires_at=invitation.expires_at,
        created_at=invitation.created_at,
    )


async def list_invitations(session: AsyncSession, ctx: OrgContext) -> list[schemas.InvitationOut]:
    rbac.require_permission(ctx.role, rbac.MEMBERS_MANAGE)
    stmt = (
        select(Invitation)
        .where(
            Invitation.organization_id == ctx.org.id,
            Invitation.accepted_at.is_(None),
            Invitation.expires_at > _now(),
        )
        .order_by(Invitation.created_at.desc())
    )
    return [
        schemas.InvitationOut(
            id=i.id, email=i.email, role=i.role, expires_at=i.expires_at, created_at=i.created_at
        )
        for i in (await session.execute(stmt)).scalars().all()
    ]


async def accept_invitation(session: AsyncSession, user: User, token: str) -> schemas.OrgOut:
    stmt = select(Invitation).where(
        Invitation.token_hash == hash_token(token),
        Invitation.accepted_at.is_(None),
        Invitation.expires_at > _now(),
    )
    invitation = (await session.execute(stmt)).scalar_one_or_none()
    if invitation is None:
        raise AppError("org.invitation_invalid", "Invalid or expired invitation.", 400)
    if invitation.email != user.email.lower():
        raise AppError("org.invite_email_mismatch", "This invitation was sent to a different email.", 403)

    org = await session.get(Organization, invitation.organization_id)
    if org is None or org.deleted_at is not None:
        raise AppError("org.not_found", "Organization not found.", 404)

    existing = (
        await session.execute(
            select(Membership).where(
                Membership.organization_id == org.id, Membership.user_id == user.id
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.status = "active"
        existing.role = invitation.role
    else:
        session.add(
            Membership(organization_id=org.id, user_id=user.id, role=invitation.role, status="active")
        )
    invitation.accepted_at = _now()
    await _write_audit(
        session, org.id, user.id, "invitation.accepted",
        target_type="invitation", target_id=str(invitation.id),
    )
    return _org_out(org, invitation.role)


async def revoke_invitation(session: AsyncSession, ctx: OrgContext, invitation_id: uuid.UUID) -> None:
    rbac.require_permission(ctx.role, rbac.MEMBERS_MANAGE)
    invitation = await session.get(Invitation, invitation_id)
    if invitation is None or invitation.organization_id != ctx.org.id:
        raise AppError("org.invitation_not_found", "Invitation not found.", 404)
    await session.delete(invitation)
    await _write_audit(
        session, ctx.org.id, ctx.user.id, "invitation.revoked",
        target_type="invitation", target_id=str(invitation_id),
    )


async def audit_count(session: AsyncSession, org_id: uuid.UUID) -> int:
    """Helper for tests/analytics: number of audit entries for an org."""
    stmt = select(func.count()).select_from(AuditLog).where(AuditLog.organization_id == org_id)
    return int((await session.execute(stmt)).scalar_one())
