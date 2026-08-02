"use client";

import { api, apiForm, apiStream } from "./client";
import type { ApiAgent, ApiAgentTemplate, ApiVersion } from "./types";

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

/** The role templates offered when creating an agent. Static, so it caches indefinitely. */
export function listAgentTemplates() {
  return api<ApiAgentTemplate[]>("/v1/agent-templates", { orgScoped: true });
}

/** `templateId` seeds the first draft from a role template; omitting it creates a blank agent. */
export function createAgent(name: string, opts?: { description?: string; templateId?: string }) {
  return api<ApiAgent>("/v1/agents", {
    method: "POST",
    orgScoped: true,
    body: { name, description: opts?.description, template_id: opts?.templateId ?? null },
  });
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

/** Re-point the live version at an older published one. */
export function rollbackVersion(id: string, version: number) {
  return api<ApiAgent>(`/v1/agents/${id}/rollback`, {
    method: "POST",
    orgScoped: true,
    body: { version },
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

/** The widget's appearance. Unversioned: a save is live immediately, no publish involved. */
export function getWidgetConfig(agentId: string) {
  return api<Record<string, unknown>>(`/v1/agents/${agentId}/widget-config`, { orgScoped: true });
}

export function patchWidgetConfig(agentId: string, config: Record<string, unknown>) {
  return api<Record<string, unknown>>(`/v1/agents/${agentId}/widget-config`, {
    method: "PATCH",
    orgScoped: true,
    body: config,
  });
}
