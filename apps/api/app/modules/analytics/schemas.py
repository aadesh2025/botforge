"""Analytics schemas."""

from __future__ import annotations

from pydantic import BaseModel


class ChannelBucket(BaseModel):
    """One channel's slice of the overview.

    Every channel the org has *connected* gets a bucket, including ones with no traffic
    yet — a freshly-connected WhatsApp should read as a real zero, not vanish from the
    breakdown. Rates are 0.0 on zero conversations (the UI renders that as an em dash,
    since 0% resolution would read as failure rather than "nothing happened yet").
    """

    channel: str
    conversations: int
    messages: int
    tokens_prompt: int
    tokens_completion: int
    cost_micros: int
    handoff_rate: float  # 0..1
    resolution_rate: float  # 0..1


class Overview(BaseModel):
    conversations: int
    messages: int
    users: int
    tokens_prompt: int
    tokens_completion: int
    cost_micros: int
    handoff_rate: float  # 0..1
    resolution_rate: float  # 0..1
    by_channel: list[ChannelBucket] = []


class UsageBucket(BaseModel):
    key: str  # day (ISO date) | provider | model | channel
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
