"""Inbox schemas."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from app.modules.conversations.schemas import MessageOut


class HandoffOut(BaseModel):
    id: uuid.UUID
    status: str
    requested_by: str
    reason: str | None
    assigned_to: uuid.UUID | None
    notes: list[Any]
    tags: list[str]
    created_at: dt.datetime
    resolved_at: dt.datetime | None


class InboxItemOut(BaseModel):
    id: uuid.UUID
    agent_id: uuid.UUID
    channel: str
    status: str
    title: str | None
    channel_user_id: str | None
    message_count: int
    last_message_at: dt.datetime | None
    created_at: dt.datetime
    handoff: HandoffOut | None


class InboxDetail(InboxItemOut):
    messages: list[MessageOut]


class ReplyRequest(BaseModel):
    # The chat APIs take `message`, so integrators reasonably send that here too. Accept
    # both rather than 422 on a field name that differs only by history.
    model_config = ConfigDict(populate_by_name=True)

    text: str = Field(min_length=1, max_length=8000, validation_alias=AliasChoices("text", "message"))


class AssignRequest(BaseModel):
    user_id: uuid.UUID


class NoteRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class TagsRequest(BaseModel):
    tags: list[str] = Field(default_factory=list)
