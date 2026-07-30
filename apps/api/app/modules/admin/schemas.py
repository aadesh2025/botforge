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


class AutomationBindingOut(BaseModel):
    """One BotForge tool pointing at this workflow."""

    organization_slug: str
    organization_name: str
    agent_name: str | None
    tool_name: str
    enabled: bool
    mode: str | None


class AutomationOut(BaseModel):
    """One n8n workflow, resolved to its owning org via its tags."""

    id: str
    name: str
    active: bool
    tags: list[str]
    # The org slug the tags resolve to, or the sentinels below.
    owner: str
    # "org" | "internal" | "shared-template" | "untagged" | "unknown-org"
    owner_kind: str
    organization_name: str | None = None
    webhook_url: str | None = None
    bindings: list[AutomationBindingOut] = []


class AutomationsOverviewOut(BaseModel):
    workflows: list[AutomationOut]
    # Set when n8n can't be reached or has no API key — the page says so rather than
    # rendering an empty table that looks like "no automations exist".
    error: str | None = None


class FeatureFlagOut(BaseModel):
    key: str
    enabled: bool
    description: str | None = None
    updated_at: dt.datetime


class FeatureFlagUpdate(BaseModel):
    enabled: bool
    description: str | None = None
