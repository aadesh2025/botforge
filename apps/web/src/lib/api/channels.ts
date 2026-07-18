"use client";

import { api } from "./client";

export type ChannelType = "telegram" | "whatsapp" | "slack" | "discord";

export interface ApiChannel {
  id: string;
  agent_id: string;
  type: ChannelType;
  name: string | null;
  enabled: boolean;
  config: Record<string, unknown>;
  webhook_url: string | null;
  created_at: string;
}

export function listChannels(agentId?: string) {
  const q = agentId ? `?agent_id=${agentId}` : "";
  return api<ApiChannel[]>(`/v1/channels${q}`, { orgScoped: true });
}

export function createChannel(body: {
  agent_id: string;
  type: ChannelType;
  name?: string;
  config: Record<string, unknown>;
}) {
  return api<ApiChannel>("/v1/channels", { method: "POST", orgScoped: true, body });
}

export function updateChannel(id: string, body: Record<string, unknown>) {
  return api<ApiChannel>(`/v1/channels/${id}`, { method: "PATCH", orgScoped: true, body });
}

export function deleteChannel(id: string) {
  return api<void>(`/v1/channels/${id}`, { method: "DELETE", orgScoped: true });
}

export function enableChannel(id: string) {
  return api<ApiChannel>(`/v1/channels/${id}/enable`, { method: "POST", orgScoped: true });
}

export function disableChannel(id: string) {
  return api<ApiChannel>(`/v1/channels/${id}/disable`, { method: "POST", orgScoped: true });
}
