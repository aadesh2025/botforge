/**
 * Domain types for the typed mock layer. These mirror the shapes described in
 * docs/03-DATABASE-SCHEMA.md / docs/04-API-SPEC.md so screens can be built against
 * fixtures now and swapped to the generated OpenAPI client later without churn.
 */

/** Mirrors `PROVIDER_NAMES` in `apps/api/app/llm/catalog.py`, which is the source of truth.
 *
 * The names are pinned rather than widened to `string` so a typo in a draft is a type error,
 * but nothing reads a *model* list from the client any more — that comes from
 * `GET /v1/credentials/providers`, because only the server knows which keys an org holds. */
export type Provider =
  | "groq"
  | "gemini"
  | "ollama"
  | "openrouter"
  | "cerebras"
  | "openai"
  | "anthropic"
  | "mistral"
  | "deepseek"
  | "xai"
  | "together"
  | "fireworks"
  | "custom";

export type AgentStatus = "live" | "draft" | "paused";
export type Role = "owner" | "admin" | "editor" | "viewer" | "operator";
export type Channel = "web" | "whatsapp" | "telegram" | "slack" | "discord";
export type DocStatus = "queued" | "processing" | "ready" | "failed";

export interface Organization {
  id: string;
  name: string;
  slug: string;
  plan: "free" | "pro" | "scale";
  role: Role;
}

export interface CurrentUser {
  id: string;
  name: string;
  email: string;
  initials: string;
}

export interface Agent {
  id: string;
  name: string;
  status: AgentStatus;
  provider: Provider;
  model: string;
  channels: Channel[];
  conversations7d: number;
  resolutionRate: number; // 0..1
  updatedAt: string;
}

export interface Conversation {
  id: string;
  agentName: string;
  channel: Channel;
  preview: string;
  visitor: string;
  status: "open" | "handoff" | "closed";
  messages: number;
  updatedAt: string;
}

export interface UsagePoint {
  date: string; // ISO day
  tokens: number;
  cost: number;
  conversations: number;
}

export interface DashboardSummary {
  conversations7d: number;
  conversationsDelta: number; // pct vs previous 7d
  messages7d: number;
  messagesDelta: number;
  resolutionRate: number; // 0..1
  resolutionDelta: number;
  tokens7d: number;
  cost7d: number;
  costDelta: number;
  activeAgents: number;
  totalAgents: number;
}
