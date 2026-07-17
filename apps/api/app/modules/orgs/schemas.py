"""Organization / membership / invitation schemas."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from pydantic import BaseModel, EmailStr, Field

from app.core.rbac import ASSIGNABLE_ROLES


class CreateOrgRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class UpdateOrgRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    avatar_url: str | None = Field(default=None, max_length=1024)
    settings: dict[str, Any] | None = None


class OrgOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    plan: str
    avatar_url: str | None
    role: str
    created_at: dt.datetime
    updated_at: dt.datetime


class MemberOut(BaseModel):
    user_id: uuid.UUID
    email: EmailStr
    full_name: str | None
    avatar_url: str | None
    role: str
    status: str
    joined_at: dt.datetime


class ChangeRoleRequest(BaseModel):
    role: str = Field(pattern="^(admin|editor|viewer|operator)$")


class InvitationCreate(BaseModel):
    email: EmailStr
    role: str = Field(pattern="^(admin|editor|viewer|operator)$")


class InvitationOut(BaseModel):
    id: uuid.UUID
    email: EmailStr
    role: str
    expires_at: dt.datetime
    created_at: dt.datetime


class TransferOwnershipRequest(BaseModel):
    user_id: uuid.UUID


class MessageResponse(BaseModel):
    message: str


ASSIGNABLE = set(ASSIGNABLE_ROLES)
