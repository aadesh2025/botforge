"""The streaming turn: run provider passes with an optional tool-calling loop.

A single pass when no tools/executor are supplied; otherwise: stream → if the model requests
tool calls, execute them (via `executor`), append the results, and loop — up to `max_iters`.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from app.chat.guardrails import neutralize_injections
from app.llm.base import ChatProvider, ProviderError
from app.llm.pricing import compute_cost_micros
from app.llm.types import ChatRequest, Message, StreamEvent, ToolCall, Usage

# executor(call) -> {"output": dict, "status": str, "error": str|None}
ToolExecutor = Callable[[ToolCall], Awaitable[dict[str, Any]]]


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
        return compute_cost_micros(
            self.provider,
            self.model,
            Usage(prompt_tokens=self.prompt_tokens, completion_tokens=self.completion_tokens),
        )


async def run_turn(
    provider: ChatProvider,
    req: ChatRequest,
    citations: list[dict[str, Any]],
    result: TurnResult,
    *,
    executor: ToolExecutor | None = None,
    max_iters: int = 1,
) -> AsyncIterator[StreamEvent]:
    """Stream a turn, forwarding events and accumulating into `result`.

    Emits one aggregated `done` event at the end (intermediate provider `done`s are folded in).
    """
    result.provider = provider.name
    result.model = req.model
    result.citations = citations
    if citations:
        yield StreamEvent(type="citations", citations=citations)

    messages = list(req.messages)
    iters = max_iters if (executor is not None and req.tools) else 1

    for iteration in range(iters):
        req_i = req.model_copy(update={"messages": messages})
        tool_calls: list[ToolCall] = []
        pass_content = ""
        try:
            async for ev in provider.stream(req_i):
                if ev.type == "token" and ev.delta:
                    pass_content += ev.delta
                    result.content += ev.delta
                    yield ev
                elif ev.type == "tool_call" and ev.tool_call is not None:
                    tool_calls.append(ev.tool_call)
                    yield ev
                elif ev.usage is not None:
                    result.prompt_tokens += ev.usage.prompt_tokens
                    result.completion_tokens += ev.usage.completion_tokens
                if ev.finish_reason:
                    result.finish_reason = ev.finish_reason
        except ProviderError as exc:
            result.error = str(exc)
            yield StreamEvent(type="error", error=str(exc))
            break

        # Continue the loop only if the model asked for tools and we have budget left.
        if tool_calls and executor is not None and iteration < iters - 1:
            messages.append(Message(role="assistant", content=pass_content or None, tool_calls=tool_calls))
            for call in tool_calls:
                out = await executor(call)
                result.tool_runs.append({"name": call.name, **out})
                yield StreamEvent(
                    type="tool_result",
                    tool_result={
                        "name": call.name,
                        "status": out.get("status"),
                        "output": out.get("output"),
                        "error": out.get("error"),
                    },
                )
                # Tool output is untrusted: neutralize instruction-override attempts before
                # feeding it back to the model as a tool message (treat it as data, not commands).
                tool_content = neutralize_injections(json.dumps(out.get("output") or {}))
                messages.append(
                    Message(
                        role="tool",
                        tool_call_id=call.id,
                        name=call.name,
                        content=tool_content,
                    )
                )
            continue
        break

    yield StreamEvent(
        type="done",
        usage=Usage(prompt_tokens=result.prompt_tokens, completion_tokens=result.completion_tokens),
        finish_reason=result.finish_reason or ("error" if result.error else "stop"),
    )


# Backwards-compatible single-pass helper (no tools).
async def stream_turn(
    provider: ChatProvider,
    req: ChatRequest,
    citations: list[dict[str, Any]],
    result: TurnResult,
) -> AsyncIterator[StreamEvent]:
    async for ev in run_turn(provider, req, citations, result):
        yield ev
