"use client";

import { api } from "./client";

export interface ChannelBucket {
  channel: string;
  conversations: number;
  messages: number;
  tokens_prompt: number;
  tokens_completion: number;
  cost_micros: number;
  handoff_rate: number;
  resolution_rate: number;
}

export interface Overview {
  conversations: number;
  messages: number;
  users: number;
  tokens_prompt: number;
  tokens_completion: number;
  cost_micros: number;
  handoff_rate: number;
  resolution_rate: number;
  /** One bucket per channel, including connected ones with no traffic yet. */
  by_channel: ChannelBucket[];
}

export interface UsageBucket {
  key: string;
  tokens_prompt: number;
  tokens_completion: number;
  requests: number;
  cost_micros: number;
}

export interface LatencyStats {
  count: number;
  avg_ms: number;
  p50_ms: number;
  p95_ms: number;
}

export interface QuestionCount {
  question: string;
  count: number;
}

export interface AnalyticsParams {
  agent_id?: string;
  from?: string;
  to?: string;
  group_by?: string;
  /** Narrow every metric to one channel, e.g. `instagram`. */
  channel?: string;
}

function qs(params: AnalyticsParams): string {
  const entries = Object.entries(params).filter(([, v]) => v != null && v !== "");
  return entries.length ? "?" + entries.map(([k, v]) => `${k}=${encodeURIComponent(v as string)}`).join("&") : "";
}

export function getOverview(p: AnalyticsParams = {}) {
  return api<Overview>(`/v1/analytics/overview${qs(p)}`, { orgScoped: true });
}

export function getUsage(p: AnalyticsParams & { group_by?: "day" | "provider" | "model" | "channel" } = {}) {
  return api<UsageBucket[]>(`/v1/analytics/usage${qs(p)}`, { orgScoped: true });
}

export function getLatency(p: AnalyticsParams = {}) {
  return api<LatencyStats>(`/v1/analytics/latency${qs(p)}`, { orgScoped: true });
}

export function getTopQuestions(p: AnalyticsParams = {}) {
  return api<QuestionCount[]>(`/v1/analytics/top-questions${qs(p)}`, { orgScoped: true });
}

export function getUnanswered(p: AnalyticsParams = {}) {
  return api<QuestionCount[]>(`/v1/analytics/unanswered${qs(p)}`, { orgScoped: true });
}
