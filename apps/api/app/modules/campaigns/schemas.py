"""Campaign schemas."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

Kind = Literal["widget_trigger", "broadcast"]
Status = Literal["draft", "active", "paused"]

#: Don't let a campaign fire the instant the page loads — that reads as a popup ad, and the
#: visitor hasn't had a chance to look at anything yet.
MIN_DELAY_SECONDS = 3
MAX_DELAY_SECONDS = 3600


class CampaignOut(BaseModel):
    id: uuid.UUID
    agent_id: uuid.UUID
    kind: Kind
    name: str
    message: str
    trigger_config: dict[str, Any]
    status: Status
    created_at: dt.datetime
    updated_at: dt.datetime


class CreateCampaignRequest(BaseModel):
    agent_id: uuid.UUID
    kind: Kind = "widget_trigger"
    name: str = Field(min_length=1, max_length=255)
    message: str = Field(min_length=1, max_length=2000)
    trigger_config: dict[str, Any] = Field(default_factory=dict)
    status: Status = "draft"

    @model_validator(mode="after")
    def _check(self) -> CreateCampaignRequest:
        if self.kind == "broadcast" and self.status != "draft":
            # Guarded in the service too; this catches it at the edge with a clearer message.
            raise ValueError("broadcast campaigns can only be saved as drafts for now")
        if self.kind == "widget_trigger":
            # Explicit None check: `0 or 10` would quietly turn a rejected 0 into a valid
            # default instead of telling the author their value was out of range.
            raw = self.trigger_config.get("delay_seconds")
            try:
                delay = 10 if raw is None or raw == "" else int(raw)
            except (TypeError, ValueError):
                raise ValueError("delay_seconds must be a whole number of seconds") from None
            if not MIN_DELAY_SECONDS <= delay <= MAX_DELAY_SECONDS:
                raise ValueError(
                    f"delay_seconds must be between {MIN_DELAY_SECONDS} and {MAX_DELAY_SECONDS}"
                )
            self.trigger_config = {
                "delay_seconds": delay,
                "url_pattern": str(self.trigger_config.get("url_pattern") or "").strip(),
            }
        return self


class UpdateCampaignRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    message: str | None = Field(default=None, min_length=1, max_length=2000)
    trigger_config: dict[str, Any] | None = None
    status: Status | None = None


class PublicCampaign(BaseModel):
    """What the widget needs to decide whether and when to show a message."""

    id: uuid.UUID
    message: str
    delay_seconds: int
    url_pattern: str | None
