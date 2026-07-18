import type { AgentStatus, Provider } from "./types";

export interface PersonaConfig {
  displayName: string;
  systemPrompt: string;
  tone: string;
  welcomeMessage: string;
  fallbackMessage: string;
  suggestedPrompts: string[];
  blockedTopics: string[];
}

export interface ModelConfig {
  provider: Provider;
  model: string;
  temperature: number;
  topP: number;
  maxTokens: number;
  frequencyPenalty: number;
  presencePenalty: number;
  credential: string;
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

export interface WidgetConfig {
  primaryColor: string;
  position: "bottom-right" | "bottom-left";
  launcherText: string;
  branding: boolean;
  mode: "dark" | "light";
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

export const credentialOptions = [
  { value: "org-default", label: "Organization default key" },
  { value: "byo", label: "Bring your own key" },
  { value: "custom-url", label: "Custom base URL + key" },
];

export interface KnowledgeBaseRef {
  id: string;
  name: string;
  docs: number;
  chunks: number;
  updatedAt: string;
}

export const knowledgeBases: KnowledgeBaseRef[] = [
  { id: "kb_1", name: "Product Docs", docs: 42, chunks: 1180, updatedAt: "2026-07-16T10:00:00Z" },
  { id: "kb_2", name: "Help Center FAQ", docs: 88, chunks: 940, updatedAt: "2026-07-15T14:20:00Z" },
  { id: "kb_3", name: "Shipping & Returns Policy", docs: 12, chunks: 210, updatedAt: "2026-07-10T09:05:00Z" },
];

export interface ToolRef {
  id: string;
  name: string;
  description: string;
  kind: "builtin" | "http" | "n8n";
  enabled: boolean;
}

export const tools: ToolRef[] = [
  { id: "t_ks", name: "knowledge_search", description: "Search attached knowledge bases", kind: "builtin", enabled: true },
  { id: "t_dt", name: "get_datetime", description: "Return the current date and time", kind: "builtin", enabled: true },
  { id: "t_calc", name: "calculator", description: "Evaluate arithmetic expressions", kind: "builtin", enabled: false },
  { id: "t_http", name: "http_request", description: "Guarded outbound HTTP (SSRF-protected)", kind: "builtin", enabled: false },
  { id: "t_order", name: "lookup_order", description: "GET orders.internal/api/{id}", kind: "http", enabled: true },
  { id: "t_ticket", name: "create_ticket", description: "n8n · Support ticket workflow", kind: "n8n", enabled: true },
];

export interface VersionRef {
  version: number;
  label: string;
  publishedAt: string | null;
  current: boolean;
  note: string;
}

export const versions: VersionRef[] = [
  { version: 7, label: "Draft", publishedAt: null, current: false, note: "Tightened refund policy wording" },
  { version: 6, label: "v6", publishedAt: "2026-07-16T22:10:00Z", current: true, note: "Added shipping KB + handoff" },
  { version: 5, label: "v5", publishedAt: "2026-07-12T08:30:00Z", current: false, note: "Switched to llama-3.3-70b" },
  { version: 4, label: "v4", publishedAt: "2026-07-04T16:45:00Z", current: false, note: "Initial production release" },
];

export function makeDraft(id: string): AgentDraft {
  return {
    id,
    name: "Support Concierge",
    status: "live",
    persona: {
      displayName: "Ava",
      systemPrompt:
        "You are Ava, the support concierge for AUROZEN. Answer only from the attached knowledge base. Be warm, concise, and accurate. If you are unsure or the answer isn't in the knowledge base, say so and offer to connect a human. Never invent order details, prices, or policies.",
      tone: "Friendly",
      welcomeMessage: "Hi! I'm Ava 👋 How can I help you today?",
      fallbackMessage: "I'm not fully sure about that — want me to connect you with a teammate?",
      suggestedPrompts: ["Where is my order?", "What's your return policy?", "Do you ship internationally?"],
      blockedTopics: ["competitor pricing", "legal advice"],
    },
    model: {
      provider: "groq",
      model: "llama-3.3-70b-versatile",
      temperature: 0.4,
      topP: 1,
      maxTokens: 1024,
      frequencyPenalty: 0,
      presencePenalty: 0,
      credential: "org-default",
    },
    knowledge: { attachedKbIds: ["kb_1", "kb_3"], topK: 5, scoreThreshold: 0.72, hybrid: true },
    features: { rag: true, tools: true, memory: true, handoff: true },
    widget: {
      primaryColor: "#E8590C",
      position: "bottom-right",
      launcherText: "Chat with us",
      branding: true,
      mode: "dark",
    },
  };
}
