"""Shared tool types: execution context and result."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentVersion


@dataclass(slots=True)
class ToolContext:
    """Everything a tool implementation may need at execution time."""

    session: AsyncSession
    org_id: uuid.UUID
    agent_id: uuid.UUID
    version: AgentVersion
    conversation_id: uuid.UUID | None = None


@dataclass(slots=True)
class ToolResult:
    output: dict[str, Any]
    status: str = "success"  # success | error | timeout
    error: str | None = None
