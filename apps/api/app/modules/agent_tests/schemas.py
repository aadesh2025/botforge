"""Pydantic schemas for docs/17 Phase 3 (Agent Testing, ADR-079)."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from pydantic import BaseModel, Field


class ToolCallSpec(BaseModel):
    """One entry in a test case's cached-mode script — fed into
    `app.llm.fake.MultiRoundToolProvider`."""

    name: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)


class ExpectedToolCall(BaseModel):
    """One assertion: was a call to `name` observed. `arguments=None` matches on name alone;
    a dict requires every key/value in it to be present in the actual call's arguments
    (subset match, not exact-equality — an assertion author names what matters)."""

    name: str = Field(min_length=1)
    arguments: dict[str, Any] | None = None


class HistoryTurn(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str


class CreateAgentTestRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    input_message: str = Field(min_length=1)
    input_history: list[HistoryTurn] = Field(default_factory=list)
    scripted_tool_calls: list[ToolCallSpec] = Field(default_factory=list)
    scripted_final_answer: str = ""
    expected_tool_calls: list[ExpectedToolCall] = Field(default_factory=list)
    expected_final_answer_contains: str | None = None
    enabled: bool = True


class UpdateAgentTestRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    input_message: str | None = Field(default=None, min_length=1)
    input_history: list[HistoryTurn] | None = None
    scripted_tool_calls: list[ToolCallSpec] | None = None
    scripted_final_answer: str | None = None
    expected_tool_calls: list[ExpectedToolCall] | None = None
    expected_final_answer_contains: str | None = None
    enabled: bool | None = None


class AgentTestOut(BaseModel):
    id: uuid.UUID
    agent_id: uuid.UUID
    name: str
    description: str | None
    input_message: str
    input_history: list[dict[str, Any]]
    scripted_tool_calls: list[dict[str, Any]]
    scripted_final_answer: str
    expected_tool_calls: list[dict[str, Any]]
    expected_final_answer_contains: str | None
    enabled: bool
    created_at: dt.datetime
    updated_at: dt.datetime


class RunAgentTestsRequest(BaseModel):
    # Never live by default (docs/17 Phase 3 DoD: a "live" tier must be explicitly triggered,
    # never run automatically) — the exact failure mode that exhausted the Groq free tier once
    # during the 2026-08-10 manual checklist run.
    mode: str = Field(default="cached", pattern="^(cached|live)$")
    #: Run only these test cases rather than every enabled one for the agent.
    test_ids: list[uuid.UUID] | None = None


class AgentTestRunOut(BaseModel):
    id: uuid.UUID
    agent_id: uuid.UUID
    agent_test_id: uuid.UUID
    batch_id: uuid.UUID
    mode: str
    status: str
    actual_tool_calls: list[dict[str, Any]]
    actual_final_answer: str | None
    failure_reasons: list[str]
    latency_ms: int | None
    cost_usd: float | None
    error: str | None
    started_at: dt.datetime
    completed_at: dt.datetime | None
