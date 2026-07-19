"""Platform-staff admin console routes under /v1/admin.

Every endpoint is gated by `require_staff` (user.is_staff). These routes are
deliberately org-agnostic — staff span all tenants, so there is no X-Org-Id.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models import User
from app.modules.admin import schemas, service
from app.modules.admin.deps import require_staff

router = APIRouter(prefix="/v1/admin", tags=["admin"])


@router.get("/orgs", response_model=list[schemas.OrgAdminOut])
async def list_orgs(
    _staff: User = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
) -> list[schemas.OrgAdminOut]:
    return await service.list_orgs(session)


@router.get("/users", response_model=list[schemas.UserAdminOut])
async def list_users(
    _staff: User = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
) -> list[schemas.UserAdminOut]:
    return await service.list_users(session)


@router.get("/usage", response_model=schemas.PlatformUsageOut)
async def platform_usage(
    _staff: User = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
) -> schemas.PlatformUsageOut:
    return await service.platform_usage(session)


@router.get("/health", response_model=schemas.HealthOut)
async def health(
    _staff: User = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
) -> schemas.HealthOut:
    return await service.health(session)


@router.get("/feature-flags", response_model=list[schemas.FeatureFlagOut])
async def list_flags(
    _staff: User = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
) -> list[schemas.FeatureFlagOut]:
    return await service.list_flags(session)


@router.put("/feature-flags/{key}", response_model=schemas.FeatureFlagOut)
async def upsert_flag(
    key: str,
    data: schemas.FeatureFlagUpdate,
    _staff: User = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
) -> schemas.FeatureFlagOut:
    return await service.upsert_flag(session, key, data)
