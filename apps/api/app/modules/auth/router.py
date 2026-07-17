"""Auth routes under /v1/auth."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ratelimit import rate_limit
from app.db.session import get_session
from app.models import User
from app.modules.auth import oauth, schemas, service
from app.modules.auth.deps import get_current_user

router = APIRouter(prefix="/v1/auth", tags=["auth"])


def _ctx(request: Request) -> tuple[str | None, str | None]:
    return request.headers.get("user-agent"), (request.client.host if request.client else None)


@router.post("/signup", response_model=schemas.AuthResponse, dependencies=[Depends(rate_limit("auth-signup"))])
async def signup(
    data: schemas.SignupRequest, request: Request, session: AsyncSession = Depends(get_session)
) -> schemas.AuthResponse:
    ua, ip = _ctx(request)
    return await service.signup(session, data, ua, ip)


@router.post("/login", response_model=schemas.AuthResponse, dependencies=[Depends(rate_limit("auth-login"))])
async def login(
    data: schemas.LoginRequest, request: Request, session: AsyncSession = Depends(get_session)
) -> schemas.AuthResponse:
    ua, ip = _ctx(request)
    return await service.login(session, data, ua, ip)


@router.post("/refresh", response_model=schemas.TokenPair)
async def refresh(
    data: schemas.RefreshRequest, request: Request, session: AsyncSession = Depends(get_session)
) -> schemas.TokenPair:
    ua, ip = _ctx(request)
    return await service.refresh(session, data.refresh_token, ua, ip)


@router.post("/logout", response_model=schemas.MessageResponse)
async def logout(
    data: schemas.LogoutRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> schemas.MessageResponse:
    await service.logout(session, user, data.refresh_token)
    return schemas.MessageResponse(message="Logged out.")


@router.get("/me", response_model=schemas.MeResponse)
async def me(
    session: AsyncSession = Depends(get_session), user: User = Depends(get_current_user)
) -> schemas.MeResponse:
    return await service.me(session, user)


@router.post("/verify-email", response_model=schemas.MessageResponse)
async def verify_email(
    data: schemas.VerifyEmailRequest, session: AsyncSession = Depends(get_session)
) -> schemas.MessageResponse:
    await service.verify_email(session, data.token)
    return schemas.MessageResponse(message="Email verified.")


@router.post(
    "/verify-email/resend",
    response_model=schemas.MessageResponse,
    dependencies=[Depends(rate_limit("auth-resend"))],
)
async def resend_verification(
    data: schemas.ResendVerificationRequest, session: AsyncSession = Depends(get_session)
) -> schemas.MessageResponse:
    await service.resend_verification(session, data.email)
    return schemas.MessageResponse(message="If that account needs verification, an email is on its way.")


@router.post(
    "/password/forgot",
    response_model=schemas.MessageResponse,
    dependencies=[Depends(rate_limit("auth-forgot"))],
)
async def forgot_password(
    data: schemas.ForgotPasswordRequest, session: AsyncSession = Depends(get_session)
) -> schemas.MessageResponse:
    await service.forgot_password(session, data.email)
    return schemas.MessageResponse(message="If that account exists, a reset link is on its way.")


@router.post("/password/reset", response_model=schemas.MessageResponse)
async def reset_password(
    data: schemas.ResetPasswordRequest, session: AsyncSession = Depends(get_session)
) -> schemas.MessageResponse:
    await service.reset_password(session, data.token, data.password)
    return schemas.MessageResponse(message="Password updated.")


@router.post(
    "/magic-link",
    response_model=schemas.MessageResponse,
    dependencies=[Depends(rate_limit("auth-magic"))],
)
async def magic_link(
    data: schemas.MagicLinkRequest, session: AsyncSession = Depends(get_session)
) -> schemas.MessageResponse:
    await service.magic_link(session, data.email)
    return schemas.MessageResponse(message="Check your email for a sign-in link.")


@router.post("/magic-link/verify", response_model=schemas.AuthResponse)
async def magic_link_verify(
    data: schemas.MagicLinkVerifyRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> schemas.AuthResponse:
    ua, ip = _ctx(request)
    return await service.magic_link_verify(session, data.token, ua, ip)


@router.get("/oauth/{provider}/authorize", response_model=schemas.OAuthAuthorizeResponse)
async def oauth_authorize(provider: str) -> schemas.OAuthAuthorizeResponse:
    return schemas.OAuthAuthorizeResponse(authorize_url=oauth.build_authorize_url(provider))


@router.get("/oauth/{provider}/callback", response_model=schemas.AuthResponse)
async def oauth_callback(
    provider: str, code: str, state: str, request: Request, session: AsyncSession = Depends(get_session)
) -> schemas.AuthResponse:
    verifier = oauth.pop_state(state)
    profile = await oauth.fetch_oauth_user(provider, code, verifier)
    ua, ip = _ctx(request)
    return await service.oauth_login(session, profile, ua, ip)


@router.get("/sessions", response_model=list[schemas.SessionOut])
async def list_sessions(
    session: AsyncSession = Depends(get_session), user: User = Depends(get_current_user)
) -> list[schemas.SessionOut]:
    return await service.list_sessions(session, user)


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_session(
    session_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> None:
    await service.revoke_session(session, user, session_id)
