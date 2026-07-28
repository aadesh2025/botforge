import { describe, expect, it } from "vitest";
import { CHANNEL_META, channelMeta, isNewChannel, visibleChannelTabs } from "./channel-meta";

const day = 24 * 60 * 60 * 1000;
const ago = (days: number) => new Date(Date.now() - days * day).toISOString();

describe("visibleChannelTabs", () => {
  it("always shows Web Chat, even with no channels connected", () => {
    expect(visibleChannelTabs([])).toEqual(["widget"]);
    expect(visibleChannelTabs(undefined)).toEqual(["widget"]);
  });

  it("shows a channel tab only once that channel is connected AND enabled", () => {
    // Connected but switched off — the platform isn't receiving, so there's nothing to show.
    expect(visibleChannelTabs([{ type: "instagram", enabled: false }])).toEqual(["widget"]);
    expect(visibleChannelTabs([{ type: "instagram", enabled: true }])).toEqual(["widget", "instagram"]);
  });

  it("orders tabs consistently regardless of connection order", () => {
    const channels = [
      { type: "telegram", enabled: true },
      { type: "instagram", enabled: true },
      { type: "facebook", enabled: true },
    ];
    expect(visibleChannelTabs(channels)).toEqual(["widget", "facebook", "instagram", "telegram"]);
  });

  it("de-duplicates a channel connected on several agents", () => {
    const channels = [
      { type: "whatsapp", enabled: true },
      { type: "whatsapp", enabled: true },
    ];
    expect(visibleChannelTabs(channels)).toEqual(["widget", "whatsapp"]);
  });
});

describe("isNewChannel", () => {
  it("badges a channel connected within the last week", () => {
    expect(isNewChannel([{ type: "whatsapp", enabled: true, created_at: ago(2) }], "whatsapp")).toBe(true);
  });

  it("stops badging older channels, disabled ones, and the built-in widget", () => {
    expect(isNewChannel([{ type: "whatsapp", enabled: true, created_at: ago(30) }], "whatsapp")).toBe(false);
    expect(isNewChannel([{ type: "whatsapp", enabled: false, created_at: ago(1) }], "whatsapp")).toBe(false);
    expect(isNewChannel([], "widget")).toBe(false);
  });
});

describe("channelMeta", () => {
  it("labels the Meta surfaces the way the platforms do", () => {
    expect(CHANNEL_META.facebook.label).toBe("Messenger");
    expect(CHANNEL_META.instagram.label).toBe("Instagram");
    expect(CHANNEL_META.widget.label).toBe("Web Chat");
  });

  it("falls back for legacy channel values rather than rendering undefined", () => {
    expect(channelMeta("api").label).toBe("Other");
    expect(channelMeta("api").Icon).toBeTruthy();
  });
});
