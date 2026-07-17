"""Provider-credential schemas."""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, Field


class CredentialCreate(BaseModel):
    provider: str = Field(pattern="^(groq|gemini|ollama|openrouter|openai|anthropic|custom)$")
    label: str | None = Field(default=None, max_length=255)
    api_key: str = Field(min_length=1, max_length=512)
    base_url: str | None = Field(default=None, max_length=1024)
    is_default: bool = False


class CredentialUpdate(BaseModel):
    label: str | None = Field(default=None, max_length=255)
    api_key: str | None = Field(default=None, min_length=1, max_length=512)
    base_url: str | None = Field(default=None, max_length=1024)
    is_default: bool | None = None


class CredentialOut(BaseModel):
    id: uuid.UUID
    provider: str
    label: str | None
    masked_key: str
    base_url: str | None
    is_default: bool
    created_at: dt.datetime


class ProviderInfo(BaseModel):
    name: str
    label: str
    free: bool
    requires_key: bool
    models: list[str]


class CredentialTestResult(BaseModel):
    ok: bool
    models: list[str] | None = None
    error: str | None = None
