import { create } from "zustand";
import type { ApiOrg, ApiUser } from "@/lib/api/types";

interface SessionState {
  user: ApiUser | null;
  orgs: ApiOrg[];
  activeOrgId: string | null;
  ready: boolean;
  setSession: (user: ApiUser, orgs: ApiOrg[], activeOrgId: string | null) => void;
  setOrgs: (orgs: ApiOrg[]) => void;
  setActiveOrg: (id: string) => void;
  reset: () => void;
}

export const useSession = create<SessionState>((set) => ({
  user: null,
  orgs: [],
  activeOrgId: null,
  ready: false,
  setSession: (user, orgs, activeOrgId) => set({ user, orgs, activeOrgId, ready: true }),
  setOrgs: (orgs) => set({ orgs }),
  setActiveOrg: (id) => set({ activeOrgId: id }),
  reset: () => set({ user: null, orgs: [], activeOrgId: null, ready: false }),
}));

export function activeOrg(state: SessionState): ApiOrg | null {
  return state.orgs.find((o) => o.id === state.activeOrgId) ?? state.orgs[0] ?? null;
}
