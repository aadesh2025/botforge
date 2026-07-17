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
  init: (draft: AgentDraft, agentId: string, versionNumber: number, published: boolean) => void;
  /** Mutate the draft with a producer; marks the draft dirty. */
  update: (fn: (d: AgentDraft) => void) => void;
  setPublished: (published: boolean) => void;
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
  init: (draft, agentId, versionNumber, published) =>
    set({ draft, agentId, versionNumber, published, dirty: false, saving: false, lastSavedAt: Date.now() }),
  update: (fn) => {
    const current = get().draft;
    if (!current) return;
    const next = structuredClone(current);
    fn(next);
    set({ draft: next, dirty: true });
  },
  setPublished: (published) => set({ published }),
  beginSave: () => set({ saving: true }),
  markSaved: () => set({ saving: false, dirty: false, lastSavedAt: Date.now() }),
}));
