"use client";

import { useEffect, useRef, useState } from "react";
import { CornerDownLeft, FileText, RotateCcw, Sparkles, Wrench } from "lucide-react";
import { useBuilder } from "@/lib/store/builder";
import { providerCatalog } from "@/lib/mock/builder";
import { cn } from "@/lib/utils";

interface Msg {
  id: number;
  role: "user" | "assistant";
  text: string;
  streaming?: boolean;
  citation?: string;
  tool?: string;
}

function cannedReply(input: string): { text: string; citation?: string; tool?: string } {
  const q = input.toLowerCase();
  if (q.includes("refund") || q.includes("return")) {
    return {
      text: "You can return items within 30 days of delivery for a full refund, as long as they're unused and in the original packaging. Refunds go back to your original payment method within 5–7 business days.",
      citation: "returns-policy.pdf · p2",
    };
  }
  if (q.includes("order") || q.includes("ship") || q.includes("track")) {
    return {
      text: "Let me check that for you. I've looked up your order — it shipped yesterday and is currently in transit, with delivery expected in 2–3 days. You'll get a tracking link by email shortly.",
      tool: "lookup_order",
    };
  }
  return {
    text: "Happy to help! I answer from AUROZEN's knowledge base, so I can cover orders, shipping, returns, and product questions. What would you like to know?",
  };
}

export function Playground() {
  const draft = useBuilder((s) => s.draft);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const idRef = useRef(0);

  // Seed with the welcome message whenever the draft's welcome text changes.
  useEffect(() => {
    if (!draft) return;
    setMessages([{ id: idRef.current++, role: "assistant", text: draft.persona.welcomeMessage }]);
  }, [draft?.persona.welcomeMessage]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  const send = async () => {
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    setBusy(true);

    const userId = idRef.current++;
    const botId = idRef.current++;
    setMessages((m) => [...m, { id: userId, role: "user", text }]);

    const reply = cannedReply(text);
    // small "thinking" beat, then stream tokens
    await new Promise((r) => setTimeout(r, 350));
    setMessages((m) => [
      ...m,
      { id: botId, role: "assistant", text: "", streaming: true, citation: reply.citation, tool: reply.tool },
    ]);

    const words = reply.text.split(" ");
    for (let i = 0; i < words.length; i++) {
      await new Promise((r) => setTimeout(r, 28 + Math.random() * 34));
      setMessages((m) =>
        m.map((msg) => (msg.id === botId ? { ...msg, text: words.slice(0, i + 1).join(" ") } : msg)),
      );
    }
    setMessages((m) => m.map((msg) => (msg.id === botId ? { ...msg, streaming: false } : msg)));
    setBusy(false);
  };

  const reset = () =>
    setMessages(draft ? [{ id: idRef.current++, role: "assistant", text: draft.persona.welcomeMessage }] : []);

  if (!draft) return null;
  const modelLabel = `${providerCatalog[draft.model.provider].label} · ${draft.model.model}`;

  return (
    <div className="flex h-[calc(100vh-8.5rem)] flex-col overflow-hidden rounded-lg border border-border bg-surface">
      <div className="flex items-center gap-2 border-b border-border px-4 py-3">
        <Sparkles className="size-4 text-ember-soft" />
        <span className="font-display text-sm font-semibold text-text">Playground</span>
        <span className="rounded bg-surface-2 px-1.5 py-0.5 font-mono text-[10px] text-faint">draft</span>
        <button
          onClick={reset}
          className="ml-auto inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-muted transition-colors hover:bg-surface-2 hover:text-text"
        >
          <RotateCcw className="size-3.5" /> Reset
        </button>
      </div>

      <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto p-4 scroll-thin">
        {messages.map((m) =>
          m.role === "user" ? (
            <div key={m.id} className="flex justify-end">
              <div className="max-w-[85%] rounded-2xl rounded-tr-sm bg-ember px-3.5 py-2 text-sm text-[#0A0B0D]">
                {m.text}
              </div>
            </div>
          ) : (
            <div key={m.id} className="flex flex-col gap-1.5">
              {m.tool && (
                <div className="inline-flex w-fit items-center gap-1.5 rounded-md border border-border bg-surface-2 px-2 py-1 text-[11px] text-muted">
                  <Wrench className="size-3 text-ember-soft" />
                  called <span className="font-mono text-ember-soft">{m.tool}</span>
                </div>
              )}
              <div className="max-w-[85%] rounded-2xl rounded-tl-sm border border-border bg-surface-2 px-3.5 py-2 text-sm leading-relaxed text-text">
                {m.text}
                {m.streaming && (
                  <span className="ml-0.5 inline-block h-4 w-[2px] translate-y-0.5 animate-caret-blink bg-ember" />
                )}
              </div>
              {m.citation && !m.streaming && (
                <div className="inline-flex w-fit items-center gap-1.5 rounded-md border border-ember/25 bg-ember/[0.07] px-2 py-1 text-[11px] text-ember-soft">
                  <FileText className="size-3" /> {m.citation}
                </div>
              )}
            </div>
          ),
        )}
      </div>

      <div className="border-t border-border p-3">
        <div className="flex items-end gap-2 rounded-lg border border-border bg-surface-2 p-2 focus-within:border-ember/50">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
            rows={1}
            placeholder="Message the draft agent…"
            className="max-h-28 flex-1 resize-none bg-transparent px-1 py-1.5 text-sm text-text placeholder:text-faint focus:outline-none"
          />
          <button
            onClick={send}
            disabled={!input.trim() || busy}
            className={cn(
              "grid size-8 shrink-0 place-items-center rounded-md transition-colors",
              input.trim() && !busy ? "bg-ember text-[#0A0B0D] hover:bg-ember-2" : "bg-surface-3 text-faint",
            )}
            aria-label="Send message"
          >
            <CornerDownLeft className="size-4" />
          </button>
        </div>
        <div className="mt-1.5 flex items-center justify-between px-1 text-[11px] text-faint">
          <span className="truncate font-mono">{modelLabel}</span>
          <span>temp {draft.model.temperature.toFixed(2)}</span>
        </div>
      </div>
    </div>
  );
}
