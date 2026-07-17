"""Provider protocols and the shared provider error."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from app.llm.types import ChatRequest, ChatResponse, ModelInfo, StreamEvent


class ProviderError(Exception):
    """Raised when a provider call fails in a way the fallback chain should handle."""

    def __init__(self, message: str, *, retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable


@runtime_checkable
class ChatProvider(Protocol):
    name: str

    async def chat(self, req: ChatRequest) -> ChatResponse: ...

    def stream(self, req: ChatRequest) -> AsyncIterator[StreamEvent]: ...

    def supports_tools(self) -> bool: ...

    async def list_models(self) -> list[ModelInfo]: ...


@runtime_checkable
class EmbeddingProvider(Protocol):
    dim: int

    async def embed(self, texts: list[str]) -> list[list[float]]: ...
