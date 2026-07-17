"""Password hashing, JWT access tokens, and opaque token helpers (docs/02 §5)."""

from __future__ import annotations

import datetime as dt
import hashlib
import secrets
import uuid
from typing import Any, cast

from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error
from jose import JWTError, jwt

from app.core.config import settings

_ph = PasswordHasher()

ACCESS_TTL = dt.timedelta(minutes=15)
REFRESH_TTL = dt.timedelta(days=30)
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    try:
        return _ph.verify(password_hash, password)
    except Argon2Error:
        return False


def needs_rehash(password_hash: str) -> bool:
    return _ph.check_needs_rehash(password_hash)


def create_access_token(user_id: uuid.UUID) -> str:
    now = dt.datetime.now(tz=dt.UTC)
    claims: dict[str, Any] = {
        "sub": str(user_id),
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + ACCESS_TTL).timestamp()),
        "jti": uuid.uuid4().hex,
    }
    return cast(str, jwt.encode(claims, settings.secret_key, algorithm=ALGORITHM))


def decode_access_token(token: str) -> dict[str, Any] | None:
    try:
        claims: dict[str, Any] = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except JWTError:
        return None
    if claims.get("type") != "access":
        return None
    return claims


def generate_opaque_token() -> str:
    """A high-entropy token handed to the client; only its hash is stored."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
