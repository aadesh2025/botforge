"""CRM schemas.

These describe a **person** (`CrmContact`), not a handle. The per-channel `Contact` rows
that belong to them are exposed as `channels` — that's what makes a returning customer
visibly the same human across Instagram, WhatsApp and the web widget.
"""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, Field, field_validator

#: A deliberately short, ordered funnel. Free text here would fragment into
#: "Qualified"/"qualified"/"QUALIFIED" and make the filter useless.
LEAD_STAGES = ("new", "contacted", "qualified", "customer", "lost")


class LinkedChannelOut(BaseModel):
    """One handle this person has messaged from."""

    id: uuid.UUID
    channel: str
    external_id: str
    display_name: str | None
    avatar_url: str | None


class CrmContactOut(BaseModel):
    id: uuid.UUID
    display_name: str | None
    email: str | None
    phone: str | None
    lead_stage: str | None
    order_status: str | None
    labels: list[str]
    created_at: dt.datetime
    updated_at: dt.datetime
    channels: list[LinkedChannelOut] = []
    #: Newest activity across every linked channel — the CRM list's "last active".
    last_active_at: dt.datetime | None = None
    conversation_count: int = 0


class ContactListOut(BaseModel):
    items: list[CrmContactOut]
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


class ContactDetail(CrmContactOut):
    notes: list[ContactNote]
    conversations: list[ContactConversationOut]


def _validate_stage(v: str | None) -> str | None:
    if v in (None, ""):
        return None
    if v not in LEAD_STAGES:
        raise ValueError(f"must be one of {', '.join(LEAD_STAGES)}")
    return v


class CreateContactRequest(BaseModel):
    """Operator-created contact — the one path into the CRM that isn't a chat message."""

    display_name: str = Field(min_length=1, max_length=255)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=64)
    lead_stage: str | None = Field(default=None, max_length=32)
    order_status: str | None = Field(default=None, max_length=64)

    @field_validator("lead_stage")
    @classmethod
    def _stage(cls, v: str | None) -> str | None:
        return _validate_stage(v)


class UpdateContactRequest(BaseModel):
    lead_stage: str | None = Field(default=None, max_length=32)
    order_status: str | None = Field(default=None, max_length=64)
    display_name: str | None = Field(default=None, max_length=255)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=64)

    @field_validator("lead_stage")
    @classmethod
    def _stage(cls, v: str | None) -> str | None:
        return _validate_stage(v)


class LabelsRequest(BaseModel):
    labels: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("labels")
    @classmethod
    def _clean(cls, v: list[str]) -> list[str]:
        # De-duplicated, trimmed, order preserved — labels are chips, not a sorted set.
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
