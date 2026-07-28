import { beforeEach, describe, expect, it } from "vitest";
import { useBuilder } from "./builder";
import type { AgentDraft } from "@/lib/mock/builder";

const draft = { persona: { displayName: "Ava" } } as unknown as AgentDraft;

describe("builder save state", () => {
  beforeEach(() => {
    useBuilder.getState().init(draft, "a1", 1, false);
  });

  it("clears dirty only on a successful save", () => {
    useBuilder.getState().update((d) => void (d.persona.displayName = "Nova"));
    expect(useBuilder.getState().dirty).toBe(true);

    useBuilder.getState().beginSave();
    useBuilder.getState().markSaved();

    expect(useBuilder.getState().dirty).toBe(false);
    expect(useBuilder.getState().saving).toBe(false);
    expect(useBuilder.getState().saveError).toBeNull();
  });

  it("keeps the draft dirty when a save fails", () => {
    // The autosave used try/finally with no catch, so a rejected PATCH still marked the
    // draft saved and the header read "Saved" while the edit existed only in the browser.
    useBuilder.getState().update((d) => void (d.persona.displayName = "Nova"));
    useBuilder.getState().beginSave();
    useBuilder.getState().markSaveFailed("Invalid widget configuration.");

    expect(useBuilder.getState().dirty).toBe(true);
    expect(useBuilder.getState().saving).toBe(false);
    expect(useBuilder.getState().saveError).toBe("Invalid widget configuration.");
  });

  it("clears a previous error once a later save succeeds", () => {
    useBuilder.getState().markSaveFailed("boom");
    useBuilder.getState().markSaved();
    expect(useBuilder.getState().saveError).toBeNull();
  });

  it("resets save state when a different agent loads", () => {
    useBuilder.getState().markSaveFailed("boom");
    useBuilder.getState().init(draft, "a2", 1, false);
    expect(useBuilder.getState().saveError).toBeNull();
    expect(useBuilder.getState().dirty).toBe(false);
  });
});
