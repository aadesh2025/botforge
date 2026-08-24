"use client";

// Mirror of the backend RBAC matrix (docs/02 §6, app/core/rbac.py). The server is authoritative;
// this only hides/disables UI a role cannot use.
import { useSession, activeOrg } from "@/lib/store/session";

export type Permission =
  | "org:manage"
  | "members:manage"
  | "agents:write"
  // Separate from agents:write on purpose: editing a draft is private and reversible,
  // publishing changes what every customer talks to.
  | "agents:publish"
  | "kb:manage"
  | "tools:manage"
  | "analytics:view"
  | "read"
  | "inbox:handle"
  // docs/17 Phase 2 — the same split agents:write/agents:publish already encodes.
  | "workflows:write"
  | "workflows:publish";

const ROLE_PERMISSIONS: Record<string, Permission[]> = {
  owner: ["org:manage", "members:manage", "agents:write", "agents:publish", "kb:manage", "tools:manage", "analytics:view", "read", "inbox:handle", "workflows:write", "workflows:publish"],
  admin: ["members:manage", "agents:write", "agents:publish", "kb:manage", "tools:manage", "analytics:view", "read", "inbox:handle", "workflows:write", "workflows:publish"],
  // The client role: shape, test and connect their own agent — but not put it live.
  editor: ["agents:write", "kb:manage", "tools:manage", "analytics:view", "read", "inbox:handle", "workflows:write"],
  viewer: ["analytics:view", "read"],
  operator: ["analytics:view", "read", "inbox:handle"],
};

export function hasPermission(role: string | undefined | null, perm: Permission): boolean {
  if (!role) return false;
  return (ROLE_PERMISSIONS[role] ?? []).includes(perm);
}

/** The current user's role in the active org. */
export function useRole(): string | null {
  return useSession((s) => activeOrg(s)?.role ?? null);
}

export function useCan(perm: Permission): boolean {
  const role = useRole();
  return hasPermission(role, perm);
}
