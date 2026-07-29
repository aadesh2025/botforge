import { describe, expect, it } from "vitest";
import { activeShortcutQuery, applyShortcut } from "./reply-box";

describe("activeShortcutQuery", () => {
  it("triggers on a slash at the start", () => {
    expect(activeShortcutQuery("/")).toBe("");
    expect(activeShortcutQuery("/ref")).toBe("ref");
  });

  it("triggers after whitespace, so it works mid-sentence", () => {
    expect(activeShortcutQuery("Sure thing — /ref")).toBe("ref");
  });

  it("does not trigger on a slash inside a word", () => {
    // Otherwise typing a URL or a date would pop the picker open.
    expect(activeShortcutQuery("see example.com/refunds")).toBeNull();
    expect(activeShortcutQuery("due 24/07")).toBeNull();
  });

  it("stops once the shortcut is committed with a space", () => {
    expect(activeShortcutQuery("/ref ")).toBeNull();
    expect(activeShortcutQuery("/ref and more")).toBeNull();
  });

  it("ignores a slash that isn't at the caret", () => {
    expect(activeShortcutQuery("/ref hello world")).toBeNull();
  });
});

describe("applyShortcut", () => {
  it("replaces the trigger text, keeping what came before", () => {
    expect(applyShortcut("/ref", "Your refund is on its way.")).toBe("Your refund is on its way.");
    expect(applyShortcut("Sure — /ref", "Refunded.")).toBe("Sure — Refunded.");
  });

  it("replaces a bare slash", () => {
    expect(applyShortcut("Hi /", "Hello!")).toBe("Hi Hello!");
  });

  it("leaves text alone when no trigger is active", () => {
    expect(applyShortcut("no trigger here", "X")).toBe("no trigger here");
  });

  it("only replaces the trailing trigger, not an earlier slash", () => {
    expect(applyShortcut("see a/b then /ref", "DONE")).toBe("see a/b then DONE");
  });
});
