"use client";

import { api } from "./client";
import type { ApiCredential, ApiProviderInfo, ApiProviderModels } from "./types";

export function listProviders() {
  return api<ApiProviderInfo[]>("/v1/credentials/providers", { orgScoped: true });
}

/** The provider's own model list where a key exists, else the static catalogue. */
export function listProviderModels(provider: string) {
  return api<ApiProviderModels>(`/v1/credentials/providers/${provider}/models`, { orgScoped: true });
}

/** Save this org's key for one provider, replacing any existing one.
 *
 * Omitting `api_key` keeps the stored key — the form only ever shows it masked, so editing
 * the label or endpoint must not require re-typing a secret nobody can read back. */
export function saveProviderKey(
  provider: string,
  body: { api_key?: string; base_url?: string; label?: string },
) {
  return api<ApiCredential>(`/v1/credentials/providers/${provider}`, {
    method: "PUT",
    orgScoped: true,
    body,
  });
}

export function deleteProviderKey(provider: string) {
  return api<void>(`/v1/credentials/providers/${provider}`, { method: "DELETE", orgScoped: true });
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
