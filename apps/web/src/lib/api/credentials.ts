"use client";

import { api } from "./client";
import type { ApiCredential, ApiProviderInfo } from "./types";

export function listProviders() {
  return api<ApiProviderInfo[]>("/v1/credentials/providers", { orgScoped: true });
}

export function listCredentials() {
  return api<ApiCredential[]>("/v1/credentials", { orgScoped: true });
}

export function createCredential(body: {
  provider: string;
  api_key: string;
  label?: string;
  base_url?: string;
  is_default?: boolean;
}) {
  return api<ApiCredential>("/v1/credentials", { method: "POST", orgScoped: true, body });
}

export function deleteCredential(id: string) {
  return api<void>(`/v1/credentials/${id}`, { method: "DELETE", orgScoped: true });
}

export function testCredential(id: string) {
  return api<{ ok: boolean; models: string[] | null; error: string | null }>(
    `/v1/credentials/${id}/test`,
    { method: "POST", orgScoped: true },
  );
}
