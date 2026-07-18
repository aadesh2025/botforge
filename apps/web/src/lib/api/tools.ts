"use client";

import { api } from "./client";

export interface ApiBuiltinTool {
  name: string;
  description: string;
  parameters: Record<string, unknown>;
}

export interface ApiTool {
  id: string;
  agent_id: string | null;
  name: string;
  type: "builtin" | "http";
  description: string | null;
  enabled: boolean;
  config: Record<string, unknown>;
  input_schema: Record<string, unknown>;
  created_at: string;
}

export interface ApiToolRun {
  id: string;
  tool_id: string;
  conversation_id: string | null;
  status: string;
  input: Record<string, unknown>;
  output: Record<string, unknown> | null;
  latency_ms: number | null;
  error: string | null;
  created_at: string;
}

export interface ApiToolTestResult {
  status: string;
  output: Record<string, unknown>;
  error: string | null;
  latency_ms: number;
}

export function listBuiltinTools() {
  return api<ApiBuiltinTool[]>("/v1/tools/builtin", { orgScoped: true });
}

export function listTools(agentId?: string) {
  const q = agentId ? `?agent_id=${agentId}` : "";
  return api<ApiTool[]>(`/v1/tools${q}`, { orgScoped: true });
}

export function createTool(body: {
  name: string;
  type: "builtin" | "http";
  agent_id?: string;
  description?: string;
  config?: Record<string, unknown>;
  input_schema?: Record<string, unknown>;
}) {
  return api<ApiTool>("/v1/tools", { method: "POST", orgScoped: true, body });
}

export function updateTool(id: string, body: Record<string, unknown>) {
  return api<ApiTool>(`/v1/tools/${id}`, { method: "PATCH", orgScoped: true, body });
}

export function deleteTool(id: string) {
  return api<void>(`/v1/tools/${id}`, { method: "DELETE", orgScoped: true });
}

export function testTool(id: string, input: Record<string, unknown>) {
  return api<ApiToolTestResult>(`/v1/tools/${id}/test`, { method: "POST", orgScoped: true, body: { input } });
}

export function listToolRuns(conversationId?: string) {
  const q = conversationId ? `?conversation_id=${conversationId}` : "";
  return api<ApiToolRun[]>(`/v1/tools/runs${q}`, { orgScoped: true });
}
