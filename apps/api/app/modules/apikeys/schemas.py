"""API key schemas."""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, Field


class CreateApiKeyRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    scopes: list[str] = Field(default_factory=list)
    expires_at: dt.datetime | None = None


class ApiKeyOut(BaseModel):
    id: uuid.UUID
    name: str
    key_prefix: str
    scopes: list[str]
    last_used_at: dt.datetime | None
    expires_at: dt.datetime | None
    revoked_at: dt.datetime | None
    created_at: dt.datetime


class ApiKeyCreated(ApiKeyOut):
    key: str  # full key — returned only once, on creation
