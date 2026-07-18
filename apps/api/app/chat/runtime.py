"""The streaming turn: run a provider request, forward events, accumulate a result.

Phase 8 is a single provider pass. Phase 9 wraps this with a tool-calling loop
(execute → feed back → continue) — see ``app.tools``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from app.llm.base import ChatProvider, ProviderError
from app.llm.pricing import compute_cost_micros
from app.llm.types import ChatRequest, StreamEvent


@dataclass
class TurnResult:
    """Accumulated outcome of a turn, used by callers to persist the assistant message."""

    content: str = ""
    provider: str = ""
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    finish_reason: str | None = None
    error: str | None = None
    citations: list[dict[str, Any]] = field(default_factory=list)
    tool_runs: list[dict[str, Any]] = field(default_factory=list)

    @property
    def cost_micros(self) -> int:
        from app.llm.types import Usage

        return compute_cost_micros(
            self.provider,
            self.model,
            Usage(prompt_tokens=self.prompt_tokens, completion_tokens=self.completion_tokens),
        )


async def stream_turn(
    provider: ChatProvider,
    req: ChatRequest,
    citations: list[dict[str, Any]],
    result: TurnResult,
) -> AsyncIterator[StreamEvent]:
    """Stream a single provider pass, forwarding events and accumulating into `result`."""
    result.provider = provider.name
    result.model = req.model
    result.citations = citations
    if citations:
        yield StreamEvent(type="citations", citations=citations)
    try:
        async for ev in provider.stream(req):
            if ev.type == "token" and ev.delta:
                result.content += ev.delta
            if ev.usage is not None:
                result.prompt_tokens = ev.usage.prompt_tokens
                result.completion_tokens = ev.usage.completion_tokens
            if ev.finish_reason:
                result.finish_reason = ev.finish_reason
            yield ev
    except ProviderError as exc:
        result.error = str(exc)
        yield StreamEvent(type="error", error=str(exc))
