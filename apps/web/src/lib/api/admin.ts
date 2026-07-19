"use client";

import { api } from "./client";

// Platform-staff console. These endpoints are org-agnostic (no X-Org-Id) and
// require `is_staff`; a non-staff token gets 403 from the API regardless of the UI.

export interface AdminOrg {
  id: string;
  name: string;
  slug: string | null;
  members: number;
  agents: number;
  created_at: string;
  deleted: boolean;
}

export interface AdminUser {
  id: string;
  email: string;
  is_staff: boolean;
  is_active: boolean;
  orgs: number;
  created_at: string;
}

export interface OrgUsageRow {
  organization_id: string;
  name: string;
  tokens_prompt: number;
  tokens_completion: number;
  requests: number;
  cost_micros: number;
}

export interface PlatformUsage {
  organizations: number;
  users: number;
  agents: number;
  conversations: number;
  messages: number;
  tokens_prompt: number;
  tokens_completion: number;
  cost_micros: number;
  top_orgs: OrgUsageRow[];
}

export interface AdminHealth {
  database: boolean;
  redis: boolean;
  organizations: number;
  users: number;
  conversations: number;
  messages: number;
}

export interface FeatureFlag {
  key: string;
  enabled: boolean;
  description: string | null;
  updated_at: string;
}

export const listAdminOrgs = () => api<AdminOrg[]>("/v1/admin/orgs");
export const listAdminUsers = () => api<AdminUser[]>("/v1/admin/users");
export const getPlatformUsage = () => api<PlatformUsage>("/v1/admin/usage");
export const getAdminHealth = () => api<AdminHealth>("/v1/admin/health");
export const listFeatureFlags = () => api<FeatureFlag[]>("/v1/admin/feature-flags");

export const upsertFeatureFlag = (key: string, enabled: boolean, description?: string | null) =>
  api<FeatureFlag>(`/v1/admin/feature-flags/${encodeURIComponent(key)}`, {
    method: "PUT",
    body: { enabled, description: description ?? null },
  });
