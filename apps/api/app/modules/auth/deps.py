"""Auth dependencies: resolve the current user from a Bearer access token."""

from __future__ import annotations

import uuid

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.security import decode_access_token
from app.db.session import get_session
from app.models import User

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_session),
) -> User:
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
    return user
