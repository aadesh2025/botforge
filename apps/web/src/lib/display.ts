import type { AgentStatus, Channel, Provider } from "./mock/types";

export const providerLabel: Record<Provider, string> = {
  groq: "Groq",
  gemini: "Gemini",
  ollama: "Ollama",
  openrouter: "OpenRouter",
  openai: "OpenAI",
  anthropic: "Anthropic",
  custom: "Custom",
};

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
