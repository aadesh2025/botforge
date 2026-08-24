"""Pydantic schemas for the workflow builder API (docs/17 Phase 2 §10)."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from pydantic import BaseModel, Field


class WorkflowOut(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    agent_id: uuid.UUID | None
    name: str
    description: str | None
    current_version_id: uuid.UUID | None
    created_at: dt.datetime
    updated_at: dt.datetime


class CreateWorkflowRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None


class UpdateWorkflowRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None


class WorkflowVersionOut(BaseModel):
    id: uuid.UUID
    workflow_id: uuid.UUID
    version: int
    status: str
    graph: dict[str, Any]
    created_at: dt.datetime


class CreateWorkflowVersionRequest(BaseModel):
    graph: dict[str, Any]


class WorkflowRunOut(BaseModel):
    id: uuid.UUID
    workflow_version_id: uuid.UUID
    status: str
    current_node_id: str | None
    variables: dict[str, Any]
    error: str | None
    started_at: dt.datetime
    completed_at: dt.datetime | None
    is_test: bool


class RunWorkflowRequest(BaseModel):
    # Seed variables (e.g. the triggering conversation's known fields). Empty by default —
    # a workflow that needs input declares it via Set Variable / a future trigger node.
    variables: dict[str, Any] = Field(default_factory=dict)
    conversation_id: uuid.UUID | None = None


class ResumeWorkflowRequest(BaseModel):
    decision: str = Field(pattern="^(approved|rejected)$")


class NodeRef(BaseModel):
    id: str
    type: str | None = None


class NodeChange(BaseModel):
    id: str
    type_changed: bool
    old_type: str | None
    new_type: str | None
    config_changed: bool
    old_config: dict[str, Any] | None
    new_config: dict[str, Any] | None


class EdgeRef(BaseModel):
    source: str | None
    target: str | None
    condition: str | None


class WorkflowVersionDiffOut(BaseModel):
    """Structural diff between two versions of the same workflow's graph (docs/17 Phase 4) —
    see `app.workflows.diff` for how each field is computed. Never a text/JSON diff: a node
    whose config changed is reported separately from one that was added or removed."""

    from_version: int
    to_version: int
    nodes_added: list[NodeRef]
    nodes_removed: list[NodeRef]
    nodes_changed: list[NodeChange]
    edges_added: list[EdgeRef]
    edges_removed: list[EdgeRef]
    #: Tool (builtin or MCP-provided — both share one reference namespace) names referenced by
    #: a `tool` node's `config.tool_name`, added/removed between the two versions.
    tools_added: list[str]
    tools_removed: list[str]
    #: Variable names read (via a direct config key or a `{{var}}` template) by any node.
    variables_read_added: list[str]
    variables_read_removed: list[str]
    #: Variable names written (`set_variable`, a tool/agent/sub_agent's `result_variable`, a
    #: transform's target, a loop's item/index variable) by any node.
    variables_written_added: list[str]
    variables_written_removed: list[str]


class WorkflowStepOut(BaseModel):
    id: uuid.UUID
    node_id: str
    node_type: str
    status: str
    input: dict[str, Any] | None
    output: dict[str, Any] | None
    latency_ms: int | None
    cost_usd: float | None
    error: str | None
    started_at: dt.datetime
