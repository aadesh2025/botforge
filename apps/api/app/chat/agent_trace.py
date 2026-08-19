"""Persist the agentic-loop trace `run_turn` collects on `TurnResult.agent_steps` (docs/17 §3).

Called only after the assistant `Message` row exists — `AgentStep.message_id` references it,
and message ids aren't known until `_persist_assistant_message` flushes (see
conversations/service.py `_finalize_turn`). `result.agent_steps` is empty for every turn the
agentic runtime didn't run (see `run_turn`'s `budget is not None` guard), so this is a no-op
for the overwhelming majority of turns.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentStep

if TYPE_CHECKING:
    from app.chat.runtime import TurnResult


async def persist_agent_steps(
    session: AsyncSession,
    result: TurnResult,
    *,
    conversation_id: uuid.UUID,
    organization_id: uuid.UUID,
    message_id: uuid.UUID | None,
) -> None:
    for step in result.agent_steps:
        session.add(
            AgentStep(
                organization_id=organization_id,
                conversation_id=conversation_id,
                message_id=message_id,
                step_index=step["step_index"],
                kind=step["kind"],
                tool_name=step.get("tool_name"),
                tool_input=step.get("tool_input"),
                tool_output=step.get("tool_output"),
                latency_ms=step.get("latency_ms"),
                tokens_in=step.get("tokens_in"),
                tokens_out=step.get("tokens_out"),
                cost_usd=step.get("cost_usd"),
                status=step["status"],
                error=step.get("error"),
            )
        )
