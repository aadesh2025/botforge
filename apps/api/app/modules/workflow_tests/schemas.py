"""Pydantic schemas for docs/17 Phase 4 follow-up (Workflow Testing, ADR-081)."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from pydantic import BaseModel, Field


class ScriptedNodeOutputs(BaseModel):
    """Cached-mode script (ADR-081): canned outputs for `tool`/`agent`/`sub_agent` nodes, keyed
    by what each node type's real executor callback actually receives — a graph node_id is
    never passed to an executor, so it cannot be the key here."""

    tools: dict[str, dict[str, Any]] = Field(default_factory=dict)
    agents: dict[str, dict[str, Any]] = Field(default_factory=dict)
    sub_workflows: dict[str, dict[str, Any]] = Field(default_factory=dict)


class CreateWorkflowTestRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    input_variables: dict[str, Any] = Field(default_factory=dict)
    scripted_node_outputs: ScriptedNodeOutputs = Field(default_factory=ScriptedNodeOutputs)
    expected_status: str | None = None
    expected_variables_contains: dict[str, Any] = Field(default_factory=dict)
    expected_visited_node_ids: list[str] = Field(default_factory=list)
    enabled: bool = True


class UpdateWorkflowTestRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    input_variables: dict[str, Any] | None = None
    scripted_node_outputs: ScriptedNodeOutputs | None = None
    expected_status: str | None = None
    expected_variables_contains: dict[str, Any] | None = None
    expected_visited_node_ids: list[str] | None = None
    enabled: bool | None = None


class WorkflowTestOut(BaseModel):
    id: uuid.UUID
    workflow_id: uuid.UUID
    name: str
    description: str | None
    input_variables: dict[str, Any]
    scripted_node_outputs: dict[str, Any]
    expected_status: str | None
    expected_variables_contains: dict[str, Any]
    expected_visited_node_ids: list[str]
    enabled: bool
    created_at: dt.datetime
    updated_at: dt.datetime


class RunWorkflowTestsRequest(BaseModel):
    # Never live by default (same rule as docs/17 Phase 3's RunAgentTestsRequest) — a "live"
    # tier must be explicitly triggered, never run automatically on every draft save.
    mode: str = Field(default="cached", pattern="^(cached|live)$")
    #: Run only these test cases rather than every enabled one for the workflow.
    test_ids: list[uuid.UUID] | None = None


class WorkflowTestRunOut(BaseModel):
    id: uuid.UUID
    workflow_id: uuid.UUID
    workflow_test_id: uuid.UUID
    batch_id: uuid.UUID
    mode: str
    status: str
    actual_status: str | None
    actual_variables: dict[str, Any]
    actual_visited_node_ids: list[str]
    failure_reasons: list[str]
    latency_ms: int | None
    cost_usd: float | None
    error: str | None
    started_at: dt.datetime
    completed_at: dt.datetime | None
