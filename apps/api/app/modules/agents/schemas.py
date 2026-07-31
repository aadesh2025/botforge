"""Agent and agent-version schemas.

The JSON key is ``model_config`` (per docs/04), but that name is reserved by Pydantic, so the
field is ``llm_config`` with an alias. FastAPI serializes responses by alias, so clients still
see ``model_config``.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CreateAgentRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    # Optional on purpose: omitting it keeps the original blank-agent behaviour, so nobody is
    # forced through the template picker. An unknown id is a 400, not a silent fallback.
    template_id: str | None = Field(default=None, max_length=64)


class AgentTemplateOut(BaseModel):
    """A creation-time starting point. Static catalog data — not per-org, never persisted."""

    id: str
    label: str
    icon: str
    description: str
    system_prompt: str
    welcome_message: str
    suggested_prompts: list[str]
    tone: str
    suggested_next_step: str | None


class UpdateAgentRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    is_public: bool | None = None
    status: str | None = Field(default=None, pattern="^(draft|published|archived)$")


class AgentOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    description: str | None
    status: str
    public_key: str
    is_public: bool
    current_version_id: uuid.UUID | None
    draft_version: int
    created_at: dt.datetime
    updated_at: dt.datetime


class VersionOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: uuid.UUID
    version: int
    is_published: bool
    system_prompt: str | None
    persona: dict[str, Any]
    welcome_message: str | None
    fallback_message: str | None
    suggested_prompts: list[Any]
    llm_config: dict[str, Any] = Field(alias="model_config")
    rag_config: dict[str, Any]
    features: dict[str, Any]
    created_at: dt.datetime


class UpdateVersionRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    system_prompt: str | None = None
    persona: dict[str, Any] | None = None
    welcome_message: str | None = None
    fallback_message: str | None = None
    suggested_prompts: list[Any] | None = None
    llm_config: dict[str, Any] | None = Field(default=None, alias="model_config")
    rag_config: dict[str, Any] | None = None
    features: dict[str, Any] | None = None


class RollbackRequest(BaseModel):
    version: int


class PlaygroundMessage(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str


class PlaygroundRequest(BaseModel):
    message: str = Field(min_length=1)
    history: list[PlaygroundMessage] | None = None
    stream: bool = True
