import type { AgentStatus, Provider } from "./types";

export interface PersonaConfig {
  displayName: string;
  systemPrompt: string;
  tone: string;
  welcomeMessage: string;
  fallbackMessage: string;
  suggestedPrompts: string[];
  blockedTopics: string[];
  /** The role template this agent was created from, if any. Read-only provenance — it drives
   *  the builder's next-step hint and nothing else. Null for agents started from scratch. */
  templateId: string | null;
}

/** One link in the agent's provider fallback chain (NFR-4). */
export interface FallbackEntry {
  provider: Provider;
  model: string;
}

export interface ModelConfig {
  provider: Provider;
  model: string;
  /** Tried in order when the primary provider fails before producing any output. */
  fallbacks: FallbackEntry[];
  temperature: number;
  topP: number;
  maxTokens: number;
  frequencyPenalty: number;
  presencePenalty: number;
  /** Generation halts if the model emits any of these. */
  stop: string[];
}

export interface KnowledgeConfig {
  attachedKbIds: string[];
  topK: number;
  scoreThreshold: number;
  hybrid: boolean;
}

export interface FeatureToggles {
  rag: boolean;
  tools: boolean;
  memory: boolean;
  handoff: boolean;
}

export type FloatingButtonStyle =
  | "circle-chat"
  | "circle-message"
  | "circle-dots"
  | "rounded-square"
  | "pill-text"
  | "pulse-ring";

export type WidgetFont = "system" | "inter" | "arial" | "georgia" | "courier";
export type InputBarButton = "attachment" | "emoji";

export interface WidgetConfig {
  primaryColor: string;
  position: "bottom-right" | "bottom-left";
  launcherText: string;
  branding: boolean;
  mode: "dark" | "light";
  // Extended customization — null/defaults keep the current look for untouched agents.
  widgetStyle: "solid" | "transparent";
  backgroundColor: string | null;
  textColor: string | null;
  bubbleColor: string | null;
  typingAreaColor: string | null;
  fontFamily: WidgetFont;
  logoUrl: string | null;
  floatingButtonStyle: FloatingButtonStyle | null;
  floatingButtonColor: string | null;
  inputBarButtons: InputBarButton[];
}

export interface AgentDraft {
  id: string;
  name: string;
  status: AgentStatus;
  persona: PersonaConfig;
  model: ModelConfig;
  knowledge: KnowledgeConfig;
  features: FeatureToggles;
  widget: WidgetConfig;
}

export const providerCatalog: Record<Provider, { label: string; models: string[]; free: boolean }> = {
  groq: {
    label: "Groq",
    free: true,
    models: ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768", "gemma2-9b-it"],
  },
  gemini: { label: "Google Gemini", free: true, models: ["gemini-1.5-flash", "gemini-1.5-pro"] },
  ollama: { label: "Ollama (local)", free: true, models: ["llama3.1", "qwen2.5", "phi3"] },
  openrouter: { label: "OpenRouter", free: true, models: ["meta-llama/llama-3.1-70b-instruct:free"] },
  openai: { label: "OpenAI", free: false, models: ["gpt-4o", "gpt-4o-mini", "gpt-4.1-mini"] },
  anthropic: { label: "Anthropic", free: false, models: ["claude-sonnet-5", "claude-haiku-4-5-20251001"] },
  custom: { label: "Custom endpoint", free: false, models: ["custom-model"] },
};

export const toneOptions = [
  "Friendly",
  "Professional",
  "Concise",
  "Empathetic",
  "Playful",
  "Technical",
];

// The fake `knowledgeBases`, `tools`, `versions` and `makeDraft("Support Concierge")`
// fixtures that used to live here were removed on 2026-07-30: every screen that once
// rendered them now reads the real API (see docs/PROGRESS.md). What remains is the
// builder's *type* vocabulary plus two static config lists, neither of which is
// per-tenant data — see ADR-041 for why `providerCatalog` is still a client-side list.
