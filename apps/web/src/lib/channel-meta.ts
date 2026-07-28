/** How each channel is labelled and drawn, shared by the builder and the inbox.
 *
 * Icons come from the same lucide set the builder's channel list already uses (Telegram
 * as a paper plane, WhatsApp as a handset). lucide dropped brand marks, so Instagram and
 * Messenger get generic glyphs too rather than pulling in a second icon dependency for
 * two logos.
 */

import { Camera, Globe, Hash, MessageCircle, MessageSquare, Phone, Send } from "lucide-react";
import type { ChannelType } from "./api/channels";

/** Channels a conversation can arrive on — the connectable ones plus the built-in widget. */
export type InboxChannel = ChannelType | "widget";

export interface ChannelMeta {
  label: string;
  Icon: typeof Send;
}

export const CHANNEL_META: Record<InboxChannel, ChannelMeta> = {
  widget: { label: "Web Chat", Icon: Globe },
  facebook: { label: "Messenger", Icon: MessageCircle },
  instagram: { label: "Instagram", Icon: Camera },
  whatsapp: { label: "WhatsApp", Icon: Phone },
  telegram: { label: "Telegram", Icon: Send },
  slack: { label: "Slack", Icon: Hash },
  discord: { label: "Discord", Icon: MessageSquare },
};

/** Tab order follows the reference: the always-on web chat, then the Meta surfaces. */
export const INBOX_CHANNEL_ORDER: InboxChannel[] = [
  "widget",
  "facebook",
  "instagram",
  "whatsapp",
  "telegram",
  "slack",
  "discord",
];

const FALLBACK: ChannelMeta = { label: "Other", Icon: MessageSquare };

/** Meta for any channel string, including legacy values like `web` or `api`. */
export function channelMeta(type: string): ChannelMeta {
  return CHANNEL_META[type as InboxChannel] ?? FALLBACK;
}

/** A channel counts as connected once a row exists for it *and* it's switched on. */
export type ConnectedChannel = { type: string; enabled: boolean; created_at?: string };

/**
 * Which channel tabs the inbox shows.
 *
 * Web Chat is always present — every agent has the embeddable widget inherently, there's
 * nothing to connect. Every other channel earns its tab by having at least one enabled
 * channel row in the org, so an unconnected platform simply isn't there.
 */
export function visibleChannelTabs(channels: ConnectedChannel[] | undefined): InboxChannel[] {
  const live = new Set((channels ?? []).filter((c) => c.enabled).map((c) => c.type));
  return INBOX_CHANNEL_ORDER.filter((type) => type === "widget" || live.has(type));
}

const NEW_CHANNEL_DAYS = 7;

/** Freshly connected channels get the reference's "New" badge for a week. */
export function isNewChannel(channels: ConnectedChannel[] | undefined, type: InboxChannel): boolean {
  if (type === "widget") return false;
  const cutoff = Date.now() - NEW_CHANNEL_DAYS * 24 * 60 * 60 * 1000;
  return (channels ?? []).some(
    (c) => c.type === type && c.enabled && c.created_at !== undefined && Date.parse(c.created_at) > cutoff,
  );
}
