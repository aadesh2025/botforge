"""Platform-staff gate: every admin endpoint requires `user.is_staff`."""

from __future__ import annotations

from fastapi import Depends

from app.core.errors import AppError
from app.models import User
from app.modules.auth.deps import get_current_user


async def require_staff(user: User = Depends(get_current_user)) -> User:
    """Allow only platform staff. Non-staff (and unauthenticated) requests are rejected.

    Deliberately org-agnostic: staff endpoints span all tenants, so there is no `X-Org-Id`.
    """
    if not user.is_staff:
        raise AppError("admin.forbidden", "Platform staff access required.", 403)
    return user
