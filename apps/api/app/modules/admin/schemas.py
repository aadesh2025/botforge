"""Admin console schemas."""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel


class OrgAdminOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str | None = None
    members: int
    agents: int
    #: Agents whose newest draft is ahead of what's live. A client can edit but not publish,
    #: so this is how staff notice work waiting for review without opening every builder.
    agents_with_unpublished_changes: int = 0
    created_at: dt.datetime
    deleted: bool


class UserAdminOut(BaseModel):
    id: uuid.UUID
    email: str
    is_staff: bool
    is_active: bool
    orgs: int
    created_at: dt.datetime


class OrgUsageRow(BaseModel):
    organization_id: uuid.UUID
    name: str
    tokens_prompt: int
    tokens_completion: int
    requests: int
    cost_micros: int


class PlatformUsageOut(BaseModel):
    organizations: int
    users: int
    agents: int
    conversations: int
    messages: int
    tokens_prompt: int
    tokens_completion: int
    cost_micros: int
    top_orgs: list[OrgUsageRow]


class HealthOut(BaseModel):
    database: bool
    redis: bool
    organizations: int
    users: int
    conversations: int
    messages: int


class FeatureFlagOut(BaseModel):
    key: str
    enabled: bool
    description: str | None = None
    updated_at: dt.datetime


class FeatureFlagUpdate(BaseModel):
    enabled: bool
    description: str | None = None
