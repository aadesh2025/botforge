"use client";

import { useState } from "react";
import { Check, Copy, Globe, Hash, MessageCircle, MessagesSquare, Send } from "lucide-react";
import { SectionCard } from "@/components/builder/field";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useBuilder } from "@/lib/store/builder";

const channels = [
  { key: "web", label: "Web widget", icon: Globe, connected: true },
  { key: "whatsapp", label: "WhatsApp", icon: MessageCircle, connected: true },
  { key: "telegram", label: "Telegram", icon: Send, connected: true },
  { key: "slack", label: "Slack", icon: Hash, connected: false },
  { key: "discord", label: "Discord", icon: MessagesSquare, connected: false },
];

export function ChannelsTab() {
  const draft = useBuilder((s) => s.draft);
  const [copied, setCopied] = useState(false);
  if (!draft) return null;

  const snippet = `<script src="https://cdn.botforge.ai/widget.js"
  data-agent="${draft.id}" defer></script>`;

  const copy = () => {
    navigator.clipboard?.writeText(snippet);
    setCopied(true);
    setTimeout(() => setCopied(false), 1600);
  };

  return (
    <div className="grid gap-6 lg:grid-cols-5">
      <div className="space-y-6 lg:col-span-3">
        <SectionCard title="Connected channels" description="Where people can reach this agent.">
          <ul className="space-y-2">
            {channels.map((c) => (
              <li key={c.key} className="flex items-center gap-3 rounded-md border border-border bg-surface-2/50 p-3">
                <span className="grid size-8 place-items-center rounded-md border border-border bg-surface-2 text-muted">
                  <c.icon className="size-4" />
                </span>
                <span className="flex-1 text-sm font-medium text-text">{c.label}</span>
                {c.connected ? (
                  <Badge variant="success">
                    <span className="size-1.5 rounded-full bg-success" /> Connected
                  </Badge>
                ) : (
                  <Button variant="outline" size="sm">
                    Connect
                  </Button>
                )}
              </li>
            ))}
          </ul>
        </SectionCard>

        <SectionCard title="Embed snippet" description="Paste before </body> on any page.">
          <div className="relative">
            <pre className="overflow-x-auto rounded-md border border-border bg-[#08090B] p-4 font-mono text-xs leading-relaxed text-muted scroll-thin">
              <code>{snippet}</code>
            </pre>
            <button
              onClick={copy}
              className="absolute right-2 top-2 inline-flex items-center gap-1 rounded-md border border-border bg-surface-2 px-2 py-1 text-xs text-muted transition-colors hover:text-text"
            >
              {copied ? <Check className="size-3.5 text-success" /> : <Copy className="size-3.5" />}
              {copied ? "Copied" : "Copy"}
            </button>
          </div>
        </SectionCard>
      </div>

      {/* Live widget preview */}
      <div className="lg:col-span-2">
        <div className="sticky top-32">
          <p className="mb-2 text-xs font-medium uppercase tracking-wider text-faint">Live preview</p>
          <div className="overflow-hidden rounded-xl border border-border bg-surface shadow-pop">
            <div className="flex items-center gap-2.5 bg-gradient-to-r from-ember to-ember-2 px-4 py-3">
              <span className="grid size-8 place-items-center rounded-full bg-black/15 text-sm font-bold text-[#0A0B0D]">
                {draft.persona.displayName[0]}
              </span>
              <div>
                <div className="text-sm font-semibold text-[#0A0B0D]">{draft.persona.displayName}</div>
                <div className="text-[11px] text-[#0A0B0D]/70">Online · replies instantly</div>
              </div>
            </div>
            <div className="space-y-3 bg-surface-2/40 p-4">
              <div className="max-w-[85%] rounded-2xl rounded-tl-sm border border-border bg-surface px-3 py-2 text-sm text-text">
                {draft.persona.welcomeMessage}
              </div>
              <div className="flex flex-wrap gap-1.5">
                {draft.persona.suggestedPrompts.slice(0, 3).map((p) => (
                  <span key={p} className="rounded-full border border-ember/30 bg-ember/10 px-2.5 py-1 text-xs text-ember-soft">
                    {p}
                  </span>
                ))}
              </div>
            </div>
            <div className="flex items-center gap-2 border-t border-border p-3">
              <div className="h-8 flex-1 rounded-full border border-border bg-surface-2" />
              <span className="grid size-8 place-items-center rounded-full bg-ember text-[#0A0B0D]">
                <Send className="size-4" />
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
