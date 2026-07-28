"""Provider fallback for streaming turns (NFR-4).

`registry.run_with_fallback` only covers the non-streaming `chat()` path, but every real
turn streams — so a Groq outage produced a failed turn rather than a fallback. This wraps an
ordered chain behind the `ChatProvider` protocol so the chat runtime stays unchanged.

**Fallback only happens before the first output of a pass.** Once tokens or a tool call have
reached the caller, restarting on another provider would duplicate or contradict text the
user has already seen, so a late failure is surfaced as an error instead.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from app.core.logging import get_logger
from app.llm.base import ChatProvider, ProviderError
from app.llm.types import ChatRequest, ChatResponse, ModelInfo, StreamEvent

log = get_logger("llm.fallback")


class FallbackChatProvider:
    """Try each (provider, model) in order; fall back on a retryable failure."""

    def __init__(self, chain: list[tuple[ChatProvider, str | None]]) -> None:
        if not chain:
            raise ValueError("fallback chain must not be empty")
        self._chain = chain
        # `name` and `active_model` track whichever link is serving, so usage and cost are
        # attributed to the provider that actually answered. `name` is a plain attribute
        # because the ChatProvider protocol declares it settable.
        self.name = chain[0][0].name
        self.active_model = chain[0][1]

    def _set_active(self, index: int) -> tuple[ChatProvider, str | None]:
        provider, model = self._chain[index]
        self.name = provider.name
        self.active_model = model
        return provider, model

    def supports_tools(self) -> bool:
        # Conservative: only advertise tools when every link can honour them, so a fallback
        # never silently drops the agent's tools mid-conversation.
        return all(p.supports_tools() for p, _ in self._chain)

    async def list_models(self) -> list[ModelInfo]:
        return await self._chain[0][0].list_models()

    def _request_for(self, req: ChatRequest, model: str | None) -> ChatRequest:
        return req.model_copy(update={"model": model}) if model else req

    async def chat(self, req: ChatRequest) -> ChatResponse:
        last: ProviderError | None = None
        for i in range(len(self._chain)):
            provider, model = self._set_active(i)
            try:
                return await provider.chat(self._request_for(req, model))
            except ProviderError as exc:
                last = exc
                if not exc.try_other_provider or i == len(self._chain) - 1:
                    raise
                log.warning("llm_fallback", failed=provider.name, error=str(exc))
        raise last or ProviderError("no providers available")

    async def stream(self, req: ChatRequest) -> AsyncIterator[StreamEvent]:
        for i in range(len(self._chain)):
            provider, model = self._set_active(i)
            emitted = False
            try:
                async for ev in provider.stream(self._request_for(req, model)):
                    if ev.type in ("token", "tool_call"):
                        emitted = True
                    yield ev
                return
            except ProviderError as exc:
                is_last = i == len(self._chain) - 1
                # Past the first token the caller has already seen output; swapping
                # providers now would rewrite history mid-reply.
                if emitted or not exc.try_other_provider or is_last:
                    raise
                log.warning("llm_fallback", failed=provider.name, error=str(exc))


def build_fallback_chain(
    primary: ChatProvider,
    primary_model: str | None,
    fallbacks: list[tuple[ChatProvider, str | None]],
) -> ChatProvider:
    """Return `primary` unchanged when nothing is configured, else a wrapped chain."""
    if not fallbacks:
        return primary
    return FallbackChatProvider([(primary, primary_model), *fallbacks])
