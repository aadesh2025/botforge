"""Help Center schemas."""

from __future__ import annotations

import datetime as dt
import re
import uuid

from pydantic import BaseModel, Field, field_validator

_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def slugify(value: str) -> str:
    """Title → URL-safe slug. Used when the author doesn't supply one."""
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return slug[:255] or "article"


class HelpArticleOut(BaseModel):
    id: uuid.UUID
    agent_id: uuid.UUID | None
    title: str
    slug: str
    body_markdown: str
    category: str | None
    published: bool
    sync_to_kb: bool
    kb_document_id: uuid.UUID | None
    created_at: dt.datetime
    updated_at: dt.datetime


class CreateHelpArticleRequest(BaseModel):
    agent_id: uuid.UUID
    title: str = Field(min_length=1, max_length=255)
    slug: str | None = Field(default=None, max_length=255)
    body_markdown: str = Field(min_length=1)
    category: str | None = Field(default=None, max_length=128)
    published: bool = False
    sync_to_kb: bool = False

    @field_validator("slug")
    @classmethod
    def _slug(cls, v: str | None) -> str | None:
        if v is None:
            return None
        cleaned = slugify(v)
        if not _SLUG_RE.match(cleaned):
            raise ValueError("must be lowercase words separated by hyphens")
        return cleaned


class UpdateHelpArticleRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    slug: str | None = Field(default=None, max_length=255)
    body_markdown: str | None = Field(default=None, min_length=1)
    category: str | None = Field(default=None, max_length=128)
    published: bool | None = None
    sync_to_kb: bool | None = None

    @field_validator("slug")
    @classmethod
    def _slug(cls, v: str | None) -> str | None:
        return slugify(v) if v is not None else None


# ── Public (unauthenticated) shapes ──────────────────────────────────────────────
class PublicHelpArticleSummary(BaseModel):
    title: str
    slug: str
    category: str | None
    updated_at: dt.datetime


class PublicHelpArticle(PublicHelpArticleSummary):
    body_markdown: str
