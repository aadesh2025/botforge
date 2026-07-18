"""API key schemas."""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, Field, field_validator

from app.core.rbac import SCOPES


class CreateApiKeyRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    scopes: list[str] = Field(default_factory=list)
    expires_at: dt.datetime | None = None

    @field_validator("scopes")
    @classmethod
    def _valid_scopes(cls, v: list[str]) -> list[str]:
        bad = [s for s in v if s not in SCOPES]
        if bad:
            raise ValueError(f"Invalid scopes {bad}; allowed: {list(SCOPES)}")
        return v


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
