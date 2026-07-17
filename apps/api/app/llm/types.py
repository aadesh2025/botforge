"""LLM provider-layer types (docs/06 §1)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Role = Literal["system", "user", "assistant", "tool"]


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class Message(BaseModel):
    role: Role
    content: str | None = None
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None
    name: str | None = None


class ToolSpec(BaseModel):
    name: str
    description: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)  # JSON schema


class ChatRequest(BaseModel):
    model: str
    messages: list[Message]
    temperature: float = 0.7
    top_p: float = 1.0
    max_tokens: int = 1024
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    stop: list[str] | None = None
    tools: list[ToolSpec] | None = None
    tool_choice: str | None = None
    stream: bool = False


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class ChatResponse(BaseModel):
    content: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    model: str = ""
    provider: str = ""
    usage: Usage = Field(default_factory=Usage)
    finish_reason: str | None = None


class ModelInfo(BaseModel):
    id: str
    provider: str


StreamEventType = Literal["token", "tool_call", "usage", "done", "error"]


class StreamEvent(BaseModel):
    type: StreamEventType
    delta: str | None = None
    tool_call: ToolCall | None = None
    usage: Usage | None = None
    finish_reason: str | None = None
    error: str | None = None
