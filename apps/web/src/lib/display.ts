import type { AgentStatus, Channel } from "./mock/types";

// `providerLabel` lived here until 2026-08-03. It had no importers and was a third copy of
// the provider labels (after `providerCatalog` and the server catalogue); display names now
// come from `GET /v1/credentials/providers` so they cannot disagree with what the deployment
// can actually run.

export const channelLabel: Record<Channel, string> = {
  web: "Web",
  whatsapp: "WhatsApp",
  telegram: "Telegram",
  slack: "Slack",
  discord: "Discord",
};

export const agentStatusMeta: Record<
  AgentStatus,
  { label: string; variant: "success" | "warn" | "default" }
> = {
  live: { label: "Live", variant: "success" },
  paused: { label: "Paused", variant: "warn" },
  draft: { label: "Draft", variant: "default" },
};

export const convoStatusMeta: Record<
  "open" | "handoff" | "closed",
  { label: string; variant: "info" | "ember" | "default" }
> = {
  open: { label: "Open", variant: "info" },
  handoff: { label: "Needs human", variant: "ember" },
  closed: { label: "Closed", variant: "default" },
};

/** Status meta keyed by what the API actually returns, as opposed to the mock layer's
 *  `live|draft|paused`. `agents.status` is `draft|published|archived`. */
export const apiAgentStatusMeta: Record<string, { label: string; variant: "success" | "warn" | "default" }> = {
  published: { label: "Live", variant: "success" },
  draft: { label: "Draft", variant: "default" },
  archived: { label: "Archived", variant: "warn" },
};

/** Ditto for `conversations.status` (`active|handoff|closed`) — note `active`, not `open`. */
export const apiConvoStatusMeta: Record<string, { label: string; variant: "info" | "ember" | "default" }> = {
  active: { label: "Active", variant: "info" },
  handoff: { label: "Needs human", variant: "ember" },
  closed: { label: "Closed", variant: "default" },
};
