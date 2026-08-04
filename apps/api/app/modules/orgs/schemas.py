"""Organization / membership / invitation schemas."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.chat.pii import classify_contact
from app.core.rbac import ASSIGNABLE_ROLES


class CreateOrgRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class UpdateOrgRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    avatar_url: str | None = Field(default=None, max_length=1024)
    settings: dict[str, Any] | None = None
    #: Detect contact details customers share in chat and file them in the CRM.
    auto_crm_capture_enabled: bool | None = None
    #: Contact details the agent may share with visitors (docs/11 Phase B, ADR-053/056).
    #: Anything else that looks like a contact detail is redacted from replies.
    public_contacts: list[str] | None = Field(default=None, max_length=50)

    @field_validator("public_contacts")
    @classmethod
    def _validate_contacts(cls, v: list[str] | None) -> list[str] | None:
        """Each entry must be something the redactor can actually recognise.

        Rejecting a URL or free text is deliberate rather than unhelpful: output redaction
        only acts on emails and phone numbers, so any other entry would sit in the list
        looking configured while doing nothing. A silently inert safety setting is worse
        than an error message.
        """
        if v is None:
            return None
        cleaned: list[str] = []
        for raw in v:
            entry = (raw or "").strip()
            if not entry:
                continue
            if classify_contact(entry) is None:
                raise ValueError(
                    f"{entry!r} is not a valid email address or phone number. Only contacts the "
                    f"reply filter can recognise may be allowlisted."
                )
            if entry not in cleaned:
                cleaned.append(entry)
        return cleaned


class OrgOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    plan: str
    avatar_url: str | None
    role: str
    auto_crm_capture_enabled: bool = True
    public_contacts: list[str] = []
    created_at: dt.datetime
    updated_at: dt.datetime


class MemberOut(BaseModel):
    user_id: uuid.UUID
    email: EmailStr
    full_name: str | None
    avatar_url: str | None
    role: str
    status: str
    joined_at: dt.datetime


class ChangeRoleRequest(BaseModel):
    role: str = Field(pattern="^(admin|editor|viewer|operator)$")


class InvitationCreate(BaseModel):
    email: EmailStr
    role: str = Field(pattern="^(admin|editor|viewer|operator)$")


class InvitationOut(BaseModel):
    id: uuid.UUID
    email: EmailStr
    role: str
    expires_at: dt.datetime
    created_at: dt.datetime
    # Raw accept token — returned ONLY outside production (email delivers it in prod).
    # Lets local/dev/CI accept an invite without a live SMTP inbox.
    accept_token: str | None = None


class InvitationLinkOut(BaseModel):
    """A freshly minted acceptance link for a pending invitation.

    Invitation tokens are stored hashed, so the original link cannot be read back — issuing one
    necessarily mints a new token and **invalidates any link already sent**. Callers must say so.
    """

    accept_url: str
    expires_at: dt.datetime


class TransferOwnershipRequest(BaseModel):
    user_id: uuid.UUID


class MessageResponse(BaseModel):
    message: str


ASSIGNABLE = set(ASSIGNABLE_ROLES)
