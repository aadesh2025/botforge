"use client";

// Mirror of the backend RBAC matrix (docs/02 §6, app/core/rbac.py). The server is authoritative;
// this only hides/disables UI a role cannot use.
import { useSession, activeOrg } from "@/lib/store/session";

export type Permission =
  | "org:manage"
  | "members:manage"
  | "agents:write"
  | "kb:manage"
  | "tools:manage"
  | "analytics:view"
  | "read"
  | "inbox:handle";

const ROLE_PERMISSIONS: Record<string, Permission[]> = {
  owner: ["org:manage", "members:manage", "agents:write", "kb:manage", "tools:manage", "analytics:view", "read", "inbox:handle"],
  admin: ["members:manage", "agents:write", "kb:manage", "tools:manage", "analytics:view", "read", "inbox:handle"],
  editor: ["agents:write", "kb:manage", "tools:manage", "analytics:view", "read", "inbox:handle"],
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
