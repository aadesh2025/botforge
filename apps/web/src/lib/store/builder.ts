import { create } from "zustand";
import type { AgentDraft } from "@/lib/mock/builder";

interface BuilderState {
  draft: AgentDraft | null;
  agentId: string | null;
  versionNumber: number | null;
  published: boolean;
  dirty: boolean;
  saving: boolean;
  lastSavedAt: number | null;
  /** Set when a save forked a new draft off a published version (branch-on-edit). */
  branchedToDraft: number | null;
  init: (draft: AgentDraft, agentId: string, versionNumber: number, published: boolean) => void;
  /** Mutate the draft with a producer; marks the draft dirty. */
  update: (fn: (d: AgentDraft) => void) => void;
  setPublished: (published: boolean) => void;
  /** Re-point the builder at a newly created draft version (from a branch-on-edit save). */
  retarget: (versionNumber: number) => void;
  beginSave: () => void;
  markSaved: () => void;
}

export const useBuilder = create<BuilderState>((set, get) => ({
  draft: null,
  agentId: null,
  versionNumber: null,
  published: false,
  dirty: false,
  saving: false,
  lastSavedAt: null,
  branchedToDraft: null,
  init: (draft, agentId, versionNumber, published) =>
    set({
      draft,
      agentId,
      versionNumber,
      published,
      dirty: false,
      saving: false,
      lastSavedAt: Date.now(),
      branchedToDraft: null,
    }),
  update: (fn) => {
    const current = get().draft;
    if (!current) return;
    const next = structuredClone(current);
    fn(next);
    set({ draft: next, dirty: true });
  },
  setPublished: (published) => set({ published }),
  retarget: (versionNumber) =>
    set({ versionNumber, published: false, branchedToDraft: versionNumber }),
  beginSave: () => set({ saving: true }),
  markSaved: () => set({ saving: false, dirty: false, lastSavedAt: Date.now() }),
}));
