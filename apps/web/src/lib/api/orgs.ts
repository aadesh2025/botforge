"use client";

import { api } from "./client";
import type { ApiOrg } from "./types";

export function listOrgs() {
  return api<ApiOrg[]>("/v1/orgs");
}

export function createOrg(name: string) {
  return api<ApiOrg>("/v1/orgs", { method: "POST", body: { name } });
}

// ── Members ──────────────────────────────────────────────────────────────────
export interface ApiMember {
  user_id: string;
  email: string;
  full_name: string | null;
  avatar_url: string | null;
  role: string;
  status: string;
  joined_at: string;
}

export interface ApiInvitation {
  id: string;
  email: string;
  role: string;
  status: string;
  created_at: string;
  expires_at: string;
}

export function listMembers(orgId: string) {
  return api<ApiMember[]>(`/v1/orgs/${orgId}/members`);
}

export function changeMemberRole(orgId: string, userId: string, role: string) {
  return api<{ message: string }>(`/v1/orgs/${orgId}/members/${userId}`, { method: "PATCH", body: { role } });
}

export function removeMember(orgId: string, userId: string) {
  return api<void>(`/v1/orgs/${orgId}/members/${userId}`, { method: "DELETE" });
}

export function listInvitations(orgId: string) {
  return api<ApiInvitation[]>(`/v1/orgs/${orgId}/invitations`);
}

export function createInvitation(orgId: string, email: string, role: string) {
  return api<ApiInvitation>(`/v1/orgs/${orgId}/invitations`, { method: "POST", body: { email, role } });
}

export function revokeInvitation(orgId: string, invitationId: string) {
  return api<void>(`/v1/orgs/${orgId}/invitations/${invitationId}`, { method: "DELETE" });
}
