"""Canned response schemas."""

from __future__ import annotations

import datetime as dt
import re
import uuid

from pydantic import BaseModel, Field, field_validator

#: Typed after "/" in the composer, so no whitespace and nothing that needs escaping.
SHORTCUT_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def _validate_shortcut(v: str) -> str:
    normalized = v.strip().lstrip("/").lower()
    if not SHORTCUT_RE.match(normalized):
        raise ValueError("must be lowercase letters, digits, hyphens or underscores (no spaces)")
    return normalized


class CannedResponseOut(BaseModel):
    id: uuid.UUID
    shortcut: str
    content: str
    created_at: dt.datetime
    updated_at: dt.datetime


class CreateCannedResponseRequest(BaseModel):
    shortcut: str = Field(min_length=1, max_length=64)
    content: str = Field(min_length=1, max_length=8000)

    @field_validator("shortcut")
    @classmethod
    def _shortcut(cls, v: str) -> str:
        return _validate_shortcut(v)


class UpdateCannedResponseRequest(BaseModel):
    shortcut: str | None = Field(default=None, min_length=1, max_length=64)
    content: str | None = Field(default=None, min_length=1, max_length=8000)

    @field_validator("shortcut")
    @classmethod
    def _shortcut(cls, v: str | None) -> str | None:
        return _validate_shortcut(v) if v is not None else None
