"""Tool, tool-run, and tool-test schemas."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from pydantic import BaseModel, Field


class BuiltinToolOut(BaseModel):
    name: str
    description: str
    parameters: dict[str, Any]


class CreateToolRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    type: str = Field(pattern="^(builtin|http)$")
    agent_id: uuid.UUID | None = None
    description: str | None = None
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)
    input_schema: dict[str, Any] = Field(default_factory=dict)


class UpdateToolRequest(BaseModel):
    description: str | None = None
    enabled: bool | None = None
    config: dict[str, Any] | None = None
    input_schema: dict[str, Any] | None = None


class ToolOut(BaseModel):
    id: uuid.UUID
    agent_id: uuid.UUID | None
    name: str
    type: str
    description: str | None
    enabled: bool
    config: dict[str, Any]
    input_schema: dict[str, Any]
    created_at: dt.datetime


class TestToolRequest(BaseModel):
    input: dict[str, Any] = Field(default_factory=dict)


class TestToolResponse(BaseModel):
    status: str
    output: dict[str, Any]
    error: str | None
    latency_ms: int


class ToolRunOut(BaseModel):
    id: uuid.UUID
    tool_id: uuid.UUID
    conversation_id: uuid.UUID | None
    status: str
    input: dict[str, Any]
    output: dict[str, Any] | None
    latency_ms: int | None
    error: str | None
    created_at: dt.datetime
