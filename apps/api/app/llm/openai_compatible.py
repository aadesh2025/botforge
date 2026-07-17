"""OpenAI-compatible provider + thin subclasses (Groq, Ollama, OpenRouter, OpenAI, custom)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.core.config import settings
from app.llm.base import ProviderError
from app.llm.types import (
    ChatRequest,
    ChatResponse,
    Message,
    ModelInfo,
    StreamEvent,
    ToolCall,
    Usage,
)


def _message_to_openai(m: Message) -> dict[str, Any]:
    d: dict[str, Any] = {"role": m.role}
    d["content"] = m.content
    if m.tool_calls:
        d["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
            }
            for tc in m.tool_calls
        ]
    if m.tool_call_id:
        d["tool_call_id"] = m.tool_call_id
    if m.name:
        d["name"] = m.name
    return d


def build_openai_payload(req: ChatRequest, *, stream: bool) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": req.model,
        "messages": [_message_to_openai(m) for m in req.messages],
        "temperature": req.temperature,
        "top_p": req.top_p,
        "max_tokens": req.max_tokens,
        "frequency_penalty": req.frequency_penalty,
        "presence_penalty": req.presence_penalty,
    }
    if req.stop:
        body["stop"] = req.stop
    if req.tools:
        body["tools"] = [
            {"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.parameters}}
            for t in req.tools
        ]
        if req.tool_choice:
            body["tool_choice"] = req.tool_choice
    if stream:
        body["stream"] = True
        body["stream_options"] = {"include_usage": True}
    return body


class OpenAICompatibleProvider:
    name = "openai-compatible"

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        *,
        name: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 60.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        if name:
            self.name = name
        self._transport = transport
        self._timeout = timeout

    def _client(self) -> httpx.AsyncClient:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return httpx.AsyncClient(
            base_url=self.base_url, headers=headers, timeout=self._timeout, transport=self._transport
        )

    @staticmethod
    def _raise_for_status(resp: httpx.Response) -> None:
        if resp.status_code < 400:
            return
        retryable = resp.status_code == 429 or resp.status_code >= 500
        raise ProviderError(f"provider returned {resp.status_code}: {resp.text[:200]}", retryable=retryable)

    async def chat(self, req: ChatRequest) -> ChatResponse:
        async with self._client() as client:
            try:
                resp = await client.post("/chat/completions", json=build_openai_payload(req, stream=False))
            except httpx.HTTPError as exc:
                raise ProviderError(f"network error: {exc}") from exc
            self._raise_for_status(resp)
            data = resp.json()

        choice = data["choices"][0]
        msg = choice.get("message", {})
        tool_calls = [
            ToolCall(
                id=tc.get("id", ""),
                name=tc["function"]["name"],
                arguments=json.loads(tc["function"].get("arguments") or "{}"),
            )
            for tc in msg.get("tool_calls") or []
        ]
        usage = data.get("usage") or {}
        return ChatResponse(
            content=msg.get("content") or "",
            tool_calls=tool_calls,
            model=data.get("model", req.model),
            provider=self.name,
            usage=Usage(
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
            ),
            finish_reason=choice.get("finish_reason"),
        )

    async def stream(self, req: ChatRequest) -> AsyncIterator[StreamEvent]:
        tool_acc: dict[int, dict[str, str]] = {}
        usage = Usage()
        finish_reason: str | None = None

        async with self._client() as client:
            try:
                async with client.stream(
                    "POST", "/chat/completions", json=build_openai_payload(req, stream=True)
                ) as resp:
                    if resp.status_code >= 400:
                        # Must read the body before accessing text on a streaming response.
                        body = (await resp.aread()).decode(errors="replace")[:200]
                        retryable = resp.status_code == 429 or resp.status_code >= 500
                        raise ProviderError(
                            f"provider returned {resp.status_code}: {body}", retryable=retryable
                        )
                    async for line in resp.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        payload = line[len("data:") :].strip()
                        if payload == "[DONE]":
                            break
                        chunk = json.loads(payload)
                        if chunk.get("usage"):
                            usage = Usage(
                                prompt_tokens=chunk["usage"].get("prompt_tokens", 0),
                                completion_tokens=chunk["usage"].get("completion_tokens", 0),
                            )
                        for choice in chunk.get("choices", []):
                            delta = choice.get("delta", {})
                            if delta.get("content"):
                                yield StreamEvent(type="token", delta=delta["content"])
                            for tc in delta.get("tool_calls") or []:
                                idx = tc.get("index", 0)
                                slot = tool_acc.setdefault(idx, {"id": "", "name": "", "arguments": ""})
                                if tc.get("id"):
                                    slot["id"] = tc["id"]
                                fn = tc.get("function") or {}
                                if fn.get("name"):
                                    slot["name"] = fn["name"]
                                if fn.get("arguments"):
                                    slot["arguments"] += fn["arguments"]
                            if choice.get("finish_reason"):
                                finish_reason = choice["finish_reason"]
            except httpx.HTTPError as exc:
                raise ProviderError(f"network error: {exc}") from exc

        for slot in tool_acc.values():
            yield StreamEvent(
                type="tool_call",
                tool_call=ToolCall(
                    id=slot["id"], name=slot["name"], arguments=json.loads(slot["arguments"] or "{}")
                ),
            )
        yield StreamEvent(type="done", usage=usage, finish_reason=finish_reason or "stop")

    def supports_tools(self) -> bool:
        return True

    async def list_models(self) -> list[ModelInfo]:
        async with self._client() as client:
            try:
                resp = await client.get("/models")
            except httpx.HTTPError as exc:
                raise ProviderError(f"network error: {exc}") from exc
            self._raise_for_status(resp)
            data = resp.json()
        return [ModelInfo(id=m["id"], provider=self.name) for m in data.get("data", [])]


class GroqProvider(OpenAICompatibleProvider):
    name = "groq"

    def __init__(self, api_key: str | None = None, **kw: Any) -> None:
        super().__init__("https://api.groq.com/openai/v1", api_key, name="groq", **kw)


class OpenRouterProvider(OpenAICompatibleProvider):
    name = "openrouter"

    def __init__(self, api_key: str | None = None, **kw: Any) -> None:
        super().__init__("https://openrouter.ai/api/v1", api_key, name="openrouter", **kw)


class OllamaProvider(OpenAICompatibleProvider):
    name = "ollama"

    def __init__(self, api_key: str | None = None, base_url: str | None = None, **kw: Any) -> None:
        url = (base_url or settings.ollama_base_url).rstrip("/") + "/v1"
        super().__init__(url, api_key or "ollama", name="ollama", **kw)


class OpenAIProvider(OpenAICompatibleProvider):
    name = "openai"

    def __init__(self, api_key: str | None = None, **kw: Any) -> None:
        super().__init__("https://api.openai.com/v1", api_key, name="openai", **kw)


class CustomProvider(OpenAICompatibleProvider):
    name = "custom"

    def __init__(self, base_url: str, api_key: str | None = None, **kw: Any) -> None:
        super().__init__(base_url, api_key, name="custom", **kw)
