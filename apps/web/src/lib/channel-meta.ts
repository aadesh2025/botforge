/** How each channel is labelled and drawn, shared by the builder and the inbox.
 *
 * Icons come from the same lucide set the builder's channel list already uses (Telegram
 * as a paper plane, WhatsApp as a handset). lucide dropped brand marks, so Instagram and
 * Messenger get generic glyphs too rather than pulling in a second icon dependency for
 * two logos.
 */

import {
  Camera,
  Code2,
  Globe,
  Hash,
  LayoutDashboard,
  MessageCircle,
  MessageSquare,
  Phone,
  Send,
  UserPlus,
} from "lucide-react";
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

/** Channel values a conversation can carry that are never inbox *tabs*.
 *
 * `dashboard` is the in-app playground, `api`/`web` are legacy values from before the
 * channel registry, and `manual` is a contact an operator typed into the CRM. None of them
 * can receive a message, so none of them gets a tab — `manual` especially, since it has no
 * webhook and no conversations at all.
 */
const REPORTING_ONLY: Record<string, ChannelMeta> = {
  dashboard: { label: "Dashboard", Icon: LayoutDashboard },
  api: { label: "API", Icon: Code2 },
  web: { label: "Web", Icon: Globe },
  manual: { label: "Added manually", Icon: UserPlus },
};

const FALLBACK: ChannelMeta = { label: "Other", Icon: MessageSquare };

/** Meta for any channel string, including reporting-only values like `dashboard`. */
export function channelMeta(type: string): ChannelMeta {
  return CHANNEL_META[type as InboxChannel] ?? REPORTING_ONLY[type] ?? FALLBACK;
}

/** A channel counts as connected once a row exists for it *and* it's switched on. */
export type ConnectedChannel = { type: string; enabled: boolean; created_at?: string };

/**
 * The inbox's channel tabs: every channel, always.
 *
 * These used to be filtered down to connected channels only, which hid the platforms a
 * user hasn't set up yet — precisely the ones they need to discover. Showing all of them
 * turns the tab bar into the prompt to connect, instead of requiring someone to already
 * know the builder's Channels tab exists. Connection status drives *styling*, not
 * presence — see `isChannelConnected`.
 */
export function inboxChannelTabs(): InboxChannel[] {
  return INBOX_CHANNEL_ORDER;
}

/** Whether messages can actually arrive on this channel right now. */
export function isChannelConnected(
  channels: ConnectedChannel[] | undefined,
  type: InboxChannel,
): boolean {
  if (type === "widget") return true; // always on, nothing to connect
  return (channels ?? []).some((c) => c.type === type && c.enabled);
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
