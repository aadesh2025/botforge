import type { AgentDraft } from "@/lib/mock/builder";
import type { ApiAgent, ApiVersion } from "./types";
import type { Provider } from "@/lib/mock/types";

function num(v: unknown, fallback: number): number {
  return typeof v === "number" ? v : fallback;
}

/** Map a backend agent + version into the builder's draft shape. */
export function versionToDraft(agent: ApiAgent, v: ApiVersion): AgentDraft {
  const mc = v.model_config ?? {};
  const rag = v.rag_config ?? {};
  const feat = v.features ?? {};
  const persona = v.persona ?? {};
  const w = ((persona.widget as Record<string, unknown>) ?? {}) as Record<string, unknown>;

  return {
    id: agent.id,
    name: agent.name,
    status: agent.status === "published" ? "live" : agent.status === "archived" ? "paused" : "draft",
    persona: {
      displayName: (persona.displayName as string) ?? agent.name,
      systemPrompt: v.system_prompt ?? "",
      tone: (persona.tone as string) ?? "Friendly",
      welcomeMessage: v.welcome_message ?? "",
      fallbackMessage: v.fallback_message ?? "",
      suggestedPrompts: v.suggested_prompts ?? [],
      blockedTopics: (persona.blockedTopics as string[]) ?? [],
    },
    model: {
      provider: (mc.provider as Provider) ?? "groq",
      model: (mc.model as string) ?? "llama-3.3-70b-versatile",
      temperature: num(mc.temperature, 0.7),
      topP: num(mc.top_p, 1),
      maxTokens: num(mc.max_tokens, 1024),
      frequencyPenalty: num(mc.frequency_penalty, 0),
      presencePenalty: num(mc.presence_penalty, 0),
      credential: "org-default",
    },
    knowledge: {
      attachedKbIds: (rag.knowledge_base_ids as string[]) ?? [],
      topK: num(rag.top_k, 5),
      scoreThreshold: num(rag.score_threshold, 0.7),
      hybrid: (rag.hybrid as boolean) ?? true,
    },
    features: {
      rag: (rag.enabled as boolean) ?? false,
      tools: (feat.tools_enabled as boolean) ?? false,
      memory: (feat.memory_enabled as boolean) ?? true,
      handoff: (feat.handoff_enabled as boolean) ?? false,
    },
    widget: {
      primaryColor: (w.primaryColor as string) ?? "#E8590C",
      position: (w.position as "bottom-right" | "bottom-left") ?? "bottom-right",
      launcherText: (w.launcherText as string) ?? "Chat with us",
      branding: (w.branding as boolean) ?? true,
      mode: (w.mode as "dark" | "light") ?? "dark",
    },
  };
}

/** Map the builder draft back into a version PATCH body (JSON key model_config). */
export function draftToPatch(draft: AgentDraft): Record<string, unknown> {
  const p = draft.persona;
  const m = draft.model;
  const k = draft.knowledge;
  const f = draft.features;
  return {
    system_prompt: p.systemPrompt,
    welcome_message: p.welcomeMessage,
    fallback_message: p.fallbackMessage,
    suggested_prompts: p.suggestedPrompts,
    persona: {
      displayName: p.displayName,
      tone: p.tone,
      blockedTopics: p.blockedTopics,
      widget: {
        primaryColor: draft.widget.primaryColor,
        position: draft.widget.position,
        launcherText: draft.widget.launcherText,
        branding: draft.widget.branding,
        mode: draft.widget.mode,
      },
    },
    model_config: {
      provider: m.provider,
      model: m.model,
      temperature: m.temperature,
      top_p: m.topP,
      max_tokens: m.maxTokens,
      frequency_penalty: m.frequencyPenalty,
      presence_penalty: m.presencePenalty,
    },
    rag_config: {
      enabled: f.rag,
      knowledge_base_ids: k.attachedKbIds,
      top_k: k.topK,
      score_threshold: k.scoreThreshold,
      hybrid: k.hybrid,
    },
    features: { tools_enabled: f.tools, memory_enabled: f.memory, handoff_enabled: f.handoff },
  };
}
