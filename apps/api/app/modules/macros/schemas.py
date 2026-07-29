"""Macro schemas."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

ActionType = Literal["reply", "add_tag", "assign", "resolve"]
ACTION_TYPES: tuple[str, ...] = ("reply", "add_tag", "assign", "resolve")


class MacroAction(BaseModel):
    """One step. `params` is validated per type so a macro can't be saved half-formed —
    discovering a missing tag name only when an operator runs it would be worse."""

    type: ActionType
    params: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_params(self) -> MacroAction:
        if self.type == "reply":
            text = str(self.params.get("text") or "").strip()
            canned = self.params.get("canned_response_id")
            if not text and not canned:
                raise ValueError("a reply action needs either text or canned_response_id")
        elif self.type == "add_tag":
            if not str(self.params.get("tag") or "").strip():
                raise ValueError("an add_tag action needs a tag")
        elif self.type == "assign":
            if not self.params.get("user_id"):
                raise ValueError("an assign action needs a user_id")
        return self


class MacroOut(BaseModel):
    id: uuid.UUID
    name: str
    actions: list[MacroAction]
    created_at: dt.datetime
    updated_at: dt.datetime


class CreateMacroRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    actions: list[MacroAction] = Field(default_factory=list, max_length=20)


class UpdateMacroRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    actions: list[MacroAction] | None = Field(default=None, max_length=20)


class MacroRunResult(BaseModel):
    """What the run did, so the UI can report it without re-deriving the steps."""

    macro_id: uuid.UUID
    conversation_id: uuid.UUID
    applied: list[ActionType]
