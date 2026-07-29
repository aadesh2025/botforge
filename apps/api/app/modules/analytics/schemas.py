"""Analytics schemas."""

from __future__ import annotations

import uuid

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


class AgentPerformanceBucket(BaseModel):
    """One human teammate's inbox workload.

    Distinct from the per-channel breakdown: this reports on *people*, not surfaces.
    Durations are None rather than 0 when there's nothing to average — a teammate who has
    never resolved anything hasn't achieved a 0ms resolution time.
    """

    user_id: uuid.UUID
    name: str
    handoffs: int
    avg_first_response_ms: int | None
    avg_resolution_ms: int | None
    closed_count: int
