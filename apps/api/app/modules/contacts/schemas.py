"""Contacts CRM schemas."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from pydantic import BaseModel, Field, field_validator

#: A deliberately short, ordered funnel. Free text here would fragment into
#: "Qualified"/"qualified"/"QUALIFIED" and make the filter useless.
LEAD_STAGES = ("new", "contacted", "qualified", "customer", "lost")


class ContactOut(BaseModel):
    id: uuid.UUID
    channel: str
    external_id: str
    display_name: str | None
    avatar_url: str | None
    lead_stage: str | None
    order_status: str | None
    labels: list[str]
    extra: dict[str, Any]
    created_at: dt.datetime
    updated_at: dt.datetime
    #: Newest activity across this contact's conversations — the CRM list's "last active".
    last_active_at: dt.datetime | None = None
    conversation_count: int = 0


class ContactListOut(BaseModel):
    items: list[ContactOut]
    total: int
    limit: int
    offset: int


class ContactConversationOut(BaseModel):
    id: uuid.UUID
    agent_id: uuid.UUID
    channel: str
    status: str
    title: str | None
    last_message_at: dt.datetime | None
    created_at: dt.datetime


class ContactNote(BaseModel):
    by: str
    text: str
    at: str


class ContactDetail(ContactOut):
    notes: list[ContactNote]
    conversations: list[ContactConversationOut]


class CreateContactRequest(BaseModel):
    """Operator-created contact.

    Every other `Contact` row is upserted by an inbound channel message, so it arrives with
    a real platform id. A manually-added one has none — it gets `channel="manual"` and a
    synthetic `external_id`, which keeps the `(org, channel, external_id)` uniqueness
    constraint meaningful instead of special-casing it.
    """

    display_name: str = Field(min_length=1, max_length=255)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=64)
    lead_stage: str | None = Field(default=None, max_length=32)
    order_status: str | None = Field(default=None, max_length=64)

    @field_validator("lead_stage")
    @classmethod
    def _stage(cls, v: str | None) -> str | None:
        if v in (None, ""):
            return None
        if v not in LEAD_STAGES:
            raise ValueError(f"must be one of {', '.join(LEAD_STAGES)}")
        return v


class UpdateContactRequest(BaseModel):
    lead_stage: str | None = Field(default=None, max_length=32)
    order_status: str | None = Field(default=None, max_length=64)
    display_name: str | None = Field(default=None, max_length=255)

    @field_validator("lead_stage")
    @classmethod
    def _stage(cls, v: str | None) -> str | None:
        if v in (None, ""):
            return None
        if v not in LEAD_STAGES:
            raise ValueError(f"must be one of {', '.join(LEAD_STAGES)}")
        return v


class LabelsRequest(BaseModel):
    labels: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("labels")
    @classmethod
    def _clean(cls, v: list[str]) -> list[str]:
        # De-duplicated, trimmed, order preserved — labels are chips, not a set the user sorts.
        seen: set[str] = set()
        out: list[str] = []
        for raw in v:
            label = raw.strip()
            if label and label.lower() not in seen:
                seen.add(label.lower())
                out.append(label[:64])
        return out


class NoteRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
