import { create } from "zustand";
import type { AgentDraft } from "@/lib/mock/builder";

interface BuilderState {
  draft: AgentDraft | null;
  dirty: boolean;
  saving: boolean;
  lastSavedAt: number | null;
  init: (draft: AgentDraft) => void;
  /** Mutate the draft with a producer; marks the draft dirty. */
  update: (fn: (d: AgentDraft) => void) => void;
  beginSave: () => void;
  markSaved: () => void;
}

export const useBuilder = create<BuilderState>((set, get) => ({
  draft: null,
  dirty: false,
  saving: false,
  lastSavedAt: null,
  init: (draft) => set({ draft, dirty: false, saving: false, lastSavedAt: Date.now() }),
  update: (fn) => {
    const current = get().draft;
    if (!current) return;
    const next = structuredClone(current);
    fn(next);
    set({ draft: next, dirty: true });
  },
  beginSave: () => set({ saving: true }),
  markSaved: () => set({ saving: false, dirty: false, lastSavedAt: Date.now() }),
}));
