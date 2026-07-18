"""Analytics schemas."""

from __future__ import annotations

from pydantic import BaseModel


class Overview(BaseModel):
    conversations: int
    messages: int
    users: int
    tokens_prompt: int
    tokens_completion: int
    cost_micros: int
    handoff_rate: float  # 0..1
    resolution_rate: float  # 0..1


class UsageBucket(BaseModel):
    key: str  # day (ISO date) | provider | model
    tokens_prompt: int
    tokens_completion: int
    requests: int
    cost_micros: int


class LatencyStats(BaseModel):
    count: int
    avg_ms: float
    p50_ms: int
    p95_ms: int


class QuestionCount(BaseModel):
    question: str
    count: int
