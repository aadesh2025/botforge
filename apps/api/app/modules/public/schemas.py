"""Public (widget) config and chat schemas."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field


class WidgetTheme(BaseModel):
    primary_color: str = "#E8590C"
    position: str = "bottom-right"  # bottom-right | bottom-left
    launcher_text: str = "Chat with us"
    branding: bool = True
    mode: str = "dark"  # dark | light


class PublicConfig(BaseModel):
    agent_id: uuid.UUID
    name: str
    welcome_message: str
    suggested_prompts: list[Any]
    theme: WidgetTheme


class Visitor(BaseModel):
    id: str | None = None
    name: str | None = None
    email: str | None = None
    metadata: dict[str, Any] | None = None


class PublicChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    conversation_id: uuid.UUID | None = None
    stream: bool = True
    visitor: Visitor | None = None
