"""Auth service — signup, login, tokens, email verification, reset, magic-link, sessions."""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.crypto import encrypt
from app.core.email import EmailMessage, get_email_backend
from app.core.errors import AppError
from app.core.security import (
    create_access_token,
    generate_opaque_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.models import (
    EmailVerificationToken,
    MagicLinkToken,
    Membership,
    OAuthAccount,
    Organization,
    PasswordResetToken,
    Session,
    User,
)
from app.modules.auth import schemas
from app.modules.auth.oauth import OAuthUser

VERIFY_TTL = dt.timedelta(hours=24)
RESET_TTL = dt.timedelta(hours=2)
MAGIC_TTL = dt.timedelta(minutes=15)
REFRESH_TTL = dt.timedelta(days=30)


def _now() -> dt.datetime:
    return dt.datetime.now(tz=dt.UTC)


def _user_out(user: User) -> schemas.UserOut:
    return schemas.UserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        avatar_url=user.avatar_url,
        is_staff=user.is_staff,
        email_verified=user.email_verified_at is not None,
        created_at=user.created_at,
    )


async def _issue_tokens(
    session: AsyncSession, user: User, user_agent: str | None, ip: str | None
) -> schemas.TokenPair:
    refresh = generate_opaque_token()
    session.add(
        Session(
            user_id=user.id,
            refresh_token_hash=hash_token(refresh),
            user_agent=user_agent,
            ip=ip,
            expires_at=_now() + REFRESH_TTL,
        )
    )
    await session.flush()
    return schemas.TokenPair(access_token=create_access_token(user.id), refresh_token=refresh)


async def _send_email(to: str, subject: str, body: str) -> None:
    await get_email_backend().send(EmailMessage(to=to, subject=subject, body=body))


async def _get_user_by_email(session: AsyncSession, email: str) -> User | None:
    stmt = select(User).where(User.email == email.lower(), User.deleted_at.is_(None))
    return (await session.execute(stmt)).scalar_one_or_none()


# ── Signup / login ────────────────────────────────────────────────────────────
async def signup(
    session: AsyncSession, data: schemas.SignupRequest, user_agent: str | None, ip: str | None
) -> schemas.AuthResponse:
    if await _get_user_by_email(session, data.email):
        raise AppError("auth.email_taken", "An account with this email already exists.", 409)

    user = User(
        email=data.email.lower(),
        password_hash=hash_password(data.password),
        full_name=data.full_name,
    )
    session.add(user)
    await session.flush()

    await _create_and_send_verification(session, user)
    tokens = await _issue_tokens(session, user, user_agent, ip)
    return schemas.AuthResponse(
        access_token=tokens.access_token, refresh_token=tokens.refresh_token, user=_user_out(user)
    )


async def login(
    session: AsyncSession, data: schemas.LoginRequest, user_agent: str | None, ip: str | None
) -> schemas.AuthResponse:
    user = await _get_user_by_email(session, data.email)
    if user is None or not verify_password(data.password, user.password_hash):
        raise AppError("auth.invalid_credentials", "Incorrect email or password.", 401)
    if not user.is_active:
        raise AppError("auth.account_inactive", "This account is disabled.", 403)

    user.last_login_at = _now()
    tokens = await _issue_tokens(session, user, user_agent, ip)
    return schemas.AuthResponse(
        access_token=tokens.access_token, refresh_token=tokens.refresh_token, user=_user_out(user)
    )


async def refresh(
    session: AsyncSession, refresh_token: str, user_agent: str | None, ip: str | None
) -> schemas.TokenPair:
    stmt = select(Session).where(
        Session.refresh_token_hash == hash_token(refresh_token),
        Session.revoked_at.is_(None),
        Session.expires_at > _now(),
    )
    current = (await session.execute(stmt)).scalar_one_or_none()
    if current is None:
        raise AppError("auth.invalid_token", "Invalid or expired refresh token.", 401)

    current.revoked_at = _now()  # rotate: the old refresh token is now dead
    user = await session.get(User, current.user_id)
    if user is None or not user.is_active:
        raise AppError("auth.invalid_token", "Invalid or expired refresh token.", 401)
    return await _issue_tokens(session, user, user_agent, ip)


async def logout(session: AsyncSession, user: User, refresh_token: str | None) -> None:
    if refresh_token:
        stmt = select(Session).where(
            Session.refresh_token_hash == hash_token(refresh_token),
            Session.user_id == user.id,
            Session.revoked_at.is_(None),
        )
        s = (await session.execute(stmt)).scalar_one_or_none()
        if s is not None:
            s.revoked_at = _now()
        return
    # No token supplied → revoke every active session (log out everywhere).
    stmt = select(Session).where(Session.user_id == user.id, Session.revoked_at.is_(None))
    for s in (await session.execute(stmt)).scalars().all():
        s.revoked_at = _now()


async def me(session: AsyncSession, user: User) -> schemas.MeResponse:
    stmt = (
        select(Membership, Organization)
        .join(Organization, Organization.id == Membership.organization_id)
        .where(Membership.user_id == user.id, Membership.status == "active")
    )
    rows = (await session.execute(stmt)).all()
    memberships = [
        schemas.MembershipOut(
            organization_id=org.id,
            organization_name=org.name,
            organization_slug=org.slug,
            role=m.role,
            status=m.status,
        )
        for m, org in rows
    ]
    return schemas.MeResponse(user=_user_out(user), memberships=memberships)


# ── Email verification ────────────────────────────────────────────────────────
async def _create_and_send_verification(session: AsyncSession, user: User) -> None:
    raw = generate_opaque_token()
    session.add(
        EmailVerificationToken(
            user_id=user.id, token_hash=hash_token(raw), expires_at=_now() + VERIFY_TTL
        )
    )
    link = f"{settings.web_base_url}/verify?token={raw}"
    await _send_email(user.email, "Verify your email", f"Confirm your email: {link}\nToken: {raw}")


async def verify_email(session: AsyncSession, token: str) -> None:
    stmt = select(EmailVerificationToken).where(
        EmailVerificationToken.token_hash == hash_token(token),
        EmailVerificationToken.used_at.is_(None),
        EmailVerificationToken.expires_at > _now(),
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise AppError("auth.invalid_token", "Invalid or expired verification token.", 400)
    row.used_at = _now()
    user = await session.get(User, row.user_id)
    if user is not None and user.email_verified_at is None:
        user.email_verified_at = _now()


async def resend_verification(session: AsyncSession, email: str) -> None:
    user = await _get_user_by_email(session, email)
    if user is not None and user.email_verified_at is None:
        await _create_and_send_verification(session, user)


# ── Password reset ────────────────────────────────────────────────────────────
async def forgot_password(session: AsyncSession, email: str) -> None:
    user = await _get_user_by_email(session, email)
    if user is None:
        return  # do not reveal whether the account exists
    raw = generate_opaque_token()
    session.add(
        PasswordResetToken(user_id=user.id, token_hash=hash_token(raw), expires_at=_now() + RESET_TTL)
    )
    link = f"{settings.web_base_url}/reset?token={raw}"
    await _send_email(user.email, "Reset your password", f"Reset your password: {link}\nToken: {raw}")


async def reset_password(session: AsyncSession, token: str, new_password: str) -> None:
    stmt = select(PasswordResetToken).where(
        PasswordResetToken.token_hash == hash_token(token),
        PasswordResetToken.used_at.is_(None),
        PasswordResetToken.expires_at > _now(),
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise AppError("auth.invalid_token", "Invalid or expired reset token.", 400)
    row.used_at = _now()
    user = await session.get(User, row.user_id)
    if user is None:
        raise AppError("auth.invalid_token", "Invalid or expired reset token.", 400)
    user.password_hash = hash_password(new_password)
    # Revoke all sessions so a compromised session can't survive a reset.
    active = select(Session).where(Session.user_id == user.id, Session.revoked_at.is_(None))
    for s in (await session.execute(active)).scalars().all():
        s.revoked_at = _now()


# ── Magic link (passwordless) ─────────────────────────────────────────────────
async def magic_link(session: AsyncSession, email: str) -> None:
    user = await _get_user_by_email(session, email)
    if user is None:
        user = User(email=email.lower())  # passwordless signup
        session.add(user)
        await session.flush()
    raw = generate_opaque_token()
    session.add(
        MagicLinkToken(user_id=user.id, token_hash=hash_token(raw), expires_at=_now() + MAGIC_TTL)
    )
    link = f"{settings.web_base_url}/magic?token={raw}"
    await _send_email(user.email, "Your sign-in link", f"Sign in: {link}\nToken: {raw}")


async def magic_link_verify(
    session: AsyncSession, token: str, user_agent: str | None, ip: str | None
) -> schemas.AuthResponse:
    stmt = select(MagicLinkToken).where(
        MagicLinkToken.token_hash == hash_token(token),
        MagicLinkToken.used_at.is_(None),
        MagicLinkToken.expires_at > _now(),
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise AppError("auth.invalid_token", "Invalid or expired sign-in link.", 400)
    row.used_at = _now()
    user = await session.get(User, row.user_id)
    if user is None or not user.is_active:
        raise AppError("auth.invalid_token", "Invalid or expired sign-in link.", 400)
    if user.email_verified_at is None:
        user.email_verified_at = _now()  # clicking the emailed link proves the address
    tokens = await _issue_tokens(session, user, user_agent, ip)
    return schemas.AuthResponse(
        access_token=tokens.access_token, refresh_token=tokens.refresh_token, user=_user_out(user)
    )


# ── Sessions ──────────────────────────────────────────────────────────────────
async def list_sessions(session: AsyncSession, user: User) -> list[schemas.SessionOut]:
    stmt = (
        select(Session)
        .where(Session.user_id == user.id, Session.revoked_at.is_(None))
        .order_by(Session.created_at.desc())
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [
        schemas.SessionOut(
            id=s.id,
            user_agent=s.user_agent,
            ip=s.ip,
            created_at=s.created_at,
            expires_at=s.expires_at,
            current=False,
        )
        for s in rows
    ]


async def revoke_session(session: AsyncSession, user: User, session_id: uuid.UUID) -> None:
    s = await session.get(Session, session_id)
    if s is None or s.user_id != user.id:
        raise AppError("auth.session_not_found", "Session not found.", 404)
    s.revoked_at = _now()


# ── OAuth ─────────────────────────────────────────────────────────────────────
async def oauth_login(
    session: AsyncSession, profile: OAuthUser, user_agent: str | None, ip: str | None
) -> schemas.AuthResponse:
    # 1) Already linked?
    stmt = select(OAuthAccount).where(
        OAuthAccount.provider == profile.provider,
        OAuthAccount.provider_account_id == profile.provider_account_id,
    )
    account = (await session.execute(stmt)).scalar_one_or_none()

    if account is not None:
        user = await session.get(User, account.user_id)
        if user is None:
            raise AppError("auth.invalid_token", "Linked account is missing.", 401)
    else:
        # 2) Link to an existing user by email, or 3) create a new one.
        user = await _get_user_by_email(session, profile.email)
        if user is None:
            user = User(
                email=profile.email.lower(),
                full_name=profile.full_name,
                avatar_url=profile.avatar_url,
                email_verified_at=_now(),  # the provider vouches for the address
            )
            session.add(user)
            await session.flush()
        session.add(
            OAuthAccount(
                user_id=user.id,
                provider=profile.provider,
                provider_account_id=profile.provider_account_id,
                access_token_enc=encrypt(profile.access_token) if profile.access_token else None,
                refresh_token_enc=encrypt(profile.refresh_token) if profile.refresh_token else None,
                expires_at=profile.expires_at,
            )
        )

    if not user.is_active:
        raise AppError("auth.account_inactive", "This account is disabled.", 403)
    user.last_login_at = _now()
    tokens = await _issue_tokens(session, user, user_agent, ip)
    return schemas.AuthResponse(
        access_token=tokens.access_token, refresh_token=tokens.refresh_token, user=_user_out(user)
    )
