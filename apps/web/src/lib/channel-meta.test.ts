import { describe, expect, it } from "vitest";
import {
  CHANNEL_META,
  INBOX_CHANNEL_ORDER,
  channelMeta,
  inboxChannelTabs,
  isChannelConnected,
  isNewChannel,
} from "./channel-meta";

const day = 24 * 60 * 60 * 1000;
const ago = (days: number) => new Date(Date.now() - days * day).toISOString();

describe("inboxChannelTabs", () => {
  it("returns every channel regardless of what's connected", () => {
    // The tab bar is how an operator discovers a platform they haven't set up, so the
    // set never depends on connection state.
    // Playground is last: operator testing must never push a channel a real customer is
    // waiting on further from the eye.
    const all = [
      "widget",
      "facebook",
      "instagram",
      "whatsapp",
      "telegram",
      "slack",
      "discord",
      "playground",
    ];
    expect(inboxChannelTabs()).toEqual(all);
    expect(inboxChannelTabs()).toHaveLength(8);
  });

  it("stays in a fixed order", () => {
    expect(inboxChannelTabs()).toEqual(INBOX_CHANNEL_ORDER);
  });
});

describe("isChannelConnected", () => {
  it("treats Web Chat as always connected — there's nothing to set up", () => {
    expect(isChannelConnected([], "widget")).toBe(true);
    expect(isChannelConnected(undefined, "widget")).toBe(true);
  });

  it("requires a row that is both present and enabled", () => {
    expect(isChannelConnected([{ type: "instagram", enabled: true }], "instagram")).toBe(true);
    // Connected then switched off: messages can't arrive, so it isn't connected.
    expect(isChannelConnected([{ type: "instagram", enabled: false }], "instagram")).toBe(false);
    expect(isChannelConnected([], "instagram")).toBe(false);
    expect(isChannelConnected(undefined, "instagram")).toBe(false);
  });

  it("counts a channel connected on any one agent", () => {
    const channels = [
      { type: "whatsapp", enabled: false },
      { type: "whatsapp", enabled: true },
    ];
    expect(isChannelConnected(channels, "whatsapp")).toBe(true);
  });

  it("doesn't confuse one channel's row for another's", () => {
    expect(isChannelConnected([{ type: "telegram", enabled: true }], "whatsapp")).toBe(false);
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

  it("labels reporting-only channels that never get a tab", () => {
    // Real conversation.channel values that aren't connectable surfaces.
    expect(channelMeta("dashboard").label).toBe("Dashboard");
    expect(channelMeta("api").label).toBe("API");
    // They stay out of the tab bar even now that it shows every channel.
    expect(inboxChannelTabs()).not.toContain("dashboard");
    expect(inboxChannelTabs()).not.toContain("api");
  });

  it("names playground traffic distinctly from a dashboard conversation", () => {
    // Playground turns are persisted so an operator's testing shows up in analytics. They
    // need their own label: a client reading their numbers has to be able to tell their own
    // testing apart from traffic a real customer generated.
    expect(channelMeta("playground").label).toBe("Playground");
    expect(channelMeta("playground").label).not.toBe(channelMeta("dashboard").label);
  });

  it("gives playground a tab, since it is a transcript someone reads", () => {
    // Unlike the other non-connectable values it produces a conversation a person opens.
    // Leaving it out made the inbox look like it was dropping threads that Conversations
    // listed fine.
    expect(inboxChannelTabs()).toContain("playground");
    expect(inboxChannelTabs()).not.toContain("dashboard");
  });

  it("treats playground as always connected — there is nothing to set up", () => {
    // Otherwise the tab renders a connect prompt for something with no webhook and no
    // credential behind it.
    expect(isChannelConnected([], "playground")).toBe(true);
    expect(isNewChannel([], "playground")).toBe(false);
  });

  it("falls back for a channel value it has never seen, rather than rendering undefined", () => {
    expect(channelMeta("carrier-pigeon").label).toBe("Other");
    expect(channelMeta("carrier-pigeon").Icon).toBeTruthy();
  });
});
