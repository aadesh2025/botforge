"use client";

import { api } from "./client";

export interface ApiCannedResponse {
  id: string;
  shortcut: string;
  content: string;
  created_at: string;
  updated_at: string;
}

export function listCannedResponses(q?: string) {
  const qs = q ? `?q=${encodeURIComponent(q)}` : "";
  return api<ApiCannedResponse[]>(`/v1/canned-responses${qs}`, { orgScoped: true });
}

export function createCannedResponse(shortcut: string, content: string) {
  return api<ApiCannedResponse>("/v1/canned-responses", {
    method: "POST",
    orgScoped: true,
    body: { shortcut, content },
  });
}

export function updateCannedResponse(id: string, body: { shortcut?: string; content?: string }) {
  return api<ApiCannedResponse>(`/v1/canned-responses/${id}`, { method: "PATCH", orgScoped: true, body });
}

export function deleteCannedResponse(id: string) {
  return api<void>(`/v1/canned-responses/${id}`, { method: "DELETE", orgScoped: true });
}
