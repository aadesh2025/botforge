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
  /** The address already has an account: they sign in rather than creating one. */
  account_exists: boolean;
}

/** Update org settings. Currently the auto-CRM-capture toggle; name/avatar live here too. */
export function updateOrg(
  orgId: string,
  body: {
    name?: string;
    avatar_url?: string;
    auto_crm_capture_enabled?: boolean;
    public_contacts?: string[];
  },
) {
  return api<ApiOrg>(`/v1/orgs/${orgId}`, { method: "PATCH", body });
}

/** Soft-delete an organization. Owner only (`org:manage`); the server returns 204. */
export function deleteOrg(orgId: string) {
  return api<void>(`/v1/orgs/${orgId}`, { method: "DELETE" });
}

/** Accept an invitation. Requires an authenticated user whose email matches the invite. */
export function acceptInvitation(token: string) {
  return api<ApiOrg>(`/v1/orgs/invitations/${encodeURIComponent(token)}/accept`, { method: "POST" });
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

export interface InvitationPreview {
  organization_name: string;
  role: string;
  email: string;
  /** True when the invited address already has an account — the page offers sign-in, not signup. */
  account_exists: boolean;
  expires_at: string;
}

/** Read an invitation without redeeming it. Unauthenticated — the invitee has no session yet. */
export function previewInvitation(token: string) {
  return api<InvitationPreview>(`/v1/orgs/invitations/${encodeURIComponent(token)}`);
}

/** Mint a fresh acceptance link to send by hand.
 *
 * Tokens are stored hashed, so this necessarily issues a *new* one and **invalidates any link
 * already emailed**. Warn before calling it. */
export function createInvitationLink(orgId: string, invitationId: string) {
  return api<{ accept_url: string; expires_at: string }>(
    `/v1/orgs/${orgId}/invitations/${invitationId}/link`,
    { method: "POST" },
  );
}

export function revokeInvitation(orgId: string, invitationId: string) {
  return api<void>(`/v1/orgs/${orgId}/invitations/${invitationId}`, { method: "DELETE" });
}
