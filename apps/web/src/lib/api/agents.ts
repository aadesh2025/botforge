"use client";

import { api, apiForm, apiStream } from "./client";
import type { ApiAgent, ApiVersion } from "./types";

/** Upload a widget/assistant logo for an agent. Returns the public logo URL (a relative API path). */
export function uploadWidgetLogo(agentId: string, file: File) {
  const form = new FormData();
  form.append("file", file);
  return apiForm<{ logo_url: string }>(`/v1/agents/${agentId}/widget/logo`, form);
}

export function listAgents() {
  return api<ApiAgent[]>("/v1/agents", { orgScoped: true });
}

export function getAgent(id: string) {
  return api<ApiAgent>(`/v1/agents/${id}`, { orgScoped: true });
}

export function createAgent(name: string, description?: string) {
  return api<ApiAgent>("/v1/agents", { method: "POST", orgScoped: true, body: { name, description } });
}

export function deleteAgent(id: string) {
  return api<void>(`/v1/agents/${id}`, { method: "DELETE", orgScoped: true });
}

export function duplicateAgent(id: string) {
  return api<ApiAgent>(`/v1/agents/${id}/duplicate`, { method: "POST", orgScoped: true });
}

export function listVersions(id: string) {
  return api<ApiVersion[]>(`/v1/agents/${id}/versions`, { orgScoped: true });
}

export function patchVersion(id: string, version: number, patch: Record<string, unknown>) {
  return api<ApiVersion>(`/v1/agents/${id}/versions/${version}`, {
    method: "PATCH",
    orgScoped: true,
    body: patch,
  });
}

export function publishVersion(id: string, version: number) {
  return api<ApiAgent>(`/v1/agents/${id}/versions/${version}/publish`, {
    method: "POST",
    orgScoped: true,
  });
}

export interface PlaygroundTurn {
  role: "user" | "assistant";
  content: string;
}

export function playgroundStream(
  id: string,
  message: string,
  history: PlaygroundTurn[],
  signal?: AbortSignal,
) {
  return apiStream(
    `/v1/agents/${id}/playground/chat`,
    { message, history, stream: true },
    signal,
  );
}
