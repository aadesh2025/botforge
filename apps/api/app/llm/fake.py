"""Deterministic fake providers for tests (docs/06 §6)."""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator

from app.llm.base import ProviderError
from app.llm.types import (
    ChatRequest,
    ChatResponse,
    ModelInfo,
    StreamEvent,
    ToolCall,
    Usage,
)


class FakeChatProvider:
    """Echoes the last user message. Can be told to emit one tool call."""

    def __init__(self, name: str = "fake", tool_call: ToolCall | None = None) -> None:
        self.name = name
        self._tool_call = tool_call

    def _reply(self, req: ChatRequest) -> str:
        last_user = next((m.content for m in reversed(req.messages) if m.role == "user"), "")
        return f"echo: {last_user or ''}".strip()

    async def chat(self, req: ChatRequest) -> ChatResponse:
        if self._tool_call is not None:
            return ChatResponse(
                content="",
                tool_calls=[self._tool_call],
                model=req.model,
                provider=self.name,
                usage=Usage(prompt_tokens=10, completion_tokens=0),
                finish_reason="tool_calls",
            )
        text = self._reply(req)
        return ChatResponse(
            content=text,
            model=req.model,
            provider=self.name,
            usage=Usage(prompt_tokens=10, completion_tokens=len(text.split())),
            finish_reason="stop",
        )

    async def stream(self, req: ChatRequest) -> AsyncIterator[StreamEvent]:
        if self._tool_call is not None:
            yield StreamEvent(type="tool_call", tool_call=self._tool_call)
            yield StreamEvent(type="done", usage=Usage(prompt_tokens=10), finish_reason="tool_calls")
            return
        text = self._reply(req)
        for word in text.split():
            yield StreamEvent(type="token", delta=word + " ")
        yield StreamEvent(
            type="done",
            usage=Usage(prompt_tokens=10, completion_tokens=len(text.split())),
            finish_reason="stop",
        )

    def supports_tools(self) -> bool:
        return True

    async def list_models(self) -> list[ModelInfo]:
        return [ModelInfo(id="fake-1", provider=self.name)]


class RefusalProvider:
    """Streams a fixed refusal message. Used when a guardrail blocks the turn pre-LLM."""

    def __init__(self, message: str, name: str = "guardrail") -> None:
        self.name = name
        self._message = message

    async def chat(self, req: ChatRequest) -> ChatResponse:
        return ChatResponse(
            content=self._message,
            model=req.model,
            provider=self.name,
            usage=Usage(prompt_tokens=0, completion_tokens=0),
            finish_reason="stop",
        )

    async def stream(self, req: ChatRequest) -> AsyncIterator[StreamEvent]:
        for word in self._message.split():
            yield StreamEvent(type="token", delta=word + " ")
        yield StreamEvent(type="done", usage=Usage(prompt_tokens=0, completion_tokens=0), finish_reason="stop")

    def supports_tools(self) -> bool:
        return False

    async def list_models(self) -> list[ModelInfo]:
        return [ModelInfo(id="guardrail", provider=self.name)]


class ScriptedToolProvider:
    """Requests a tool call on the first turn, then answers using the tool result.

    Used to exercise the tool-calling loop deterministically.
    """

    def __init__(self, tool_call: ToolCall, answer: str = "done using the tool", name: str = "scripted") -> None:
        self.name = name
        self._tool_call = tool_call
        self._answer = answer
        self._calls = 0

    async def chat(self, req: ChatRequest) -> ChatResponse:  # pragma: no cover - stream path used
        return ChatResponse(content=self._answer, model=req.model, provider=self.name, finish_reason="stop")

    async def stream(self, req: ChatRequest) -> AsyncIterator[StreamEvent]:
        self._calls += 1
        if self._calls == 1:
            yield StreamEvent(type="tool_call", tool_call=self._tool_call)
            yield StreamEvent(type="done", usage=Usage(prompt_tokens=8), finish_reason="tool_calls")
            return
        for word in self._answer.split():
            yield StreamEvent(type="token", delta=word + " ")
        yield StreamEvent(type="done", usage=Usage(prompt_tokens=5, completion_tokens=4), finish_reason="stop")

    def supports_tools(self) -> bool:
        return True

    async def list_models(self) -> list[ModelInfo]:
        return [ModelInfo(id="scripted-1", provider=self.name)]


class FailingProvider:
    """Always raises — used to exercise the fallback chain."""

    def __init__(self, name: str = "failing") -> None:
        self.name = name

    async def chat(self, req: ChatRequest) -> ChatResponse:
        raise ProviderError("simulated failure")

    async def stream(self, req: ChatRequest) -> AsyncIterator[StreamEvent]:
        raise ProviderError("simulated failure")
        yield  # pragma: no cover - makes this an async generator

    def supports_tools(self) -> bool:
        return True

    async def list_models(self) -> list[ModelInfo]:
        raise ProviderError("simulated failure")


class FakeEmbeddingProvider:
    def __init__(self, dim: int = 8) -> None:
        self.dim = dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            digest = hashlib.sha256(text.encode()).digest()
            out.append([digest[i % len(digest)] / 255.0 for i in range(self.dim)])
        return out
