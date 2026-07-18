"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Check, Copy, MessageSquare } from "lucide-react";
import { Field, SectionCard } from "@/components/builder/field";
import { Switch } from "@/components/ui/switch";
import { Input } from "@/components/ui/input";
import { useBuilder } from "@/lib/store/builder";
import { getAgent } from "@/lib/api/agents";
import { API_BASE } from "@/lib/api/config";

export function ChannelsTab() {
  const draft = useBuilder((s) => s.draft);
  const agentId = useBuilder((s) => s.agentId);
  const update = useBuilder((s) => s.update);
  const [copied, setCopied] = useState(false);

  const { data: agent } = useQuery({
    queryKey: ["agent-key", agentId],
    queryFn: () => getAgent(agentId!),
    enabled: Boolean(agentId),
  });

  if (!draft) return null;
  const w = draft.widget;
  const publicKey = agent?.public_key ?? "YOUR_PUBLIC_KEY";
  const webOrigin = typeof window !== "undefined" ? window.location.origin : "";
  const snippet = `<script\n  src="${webOrigin}/widget.js"\n  data-agent="${publicKey}"\n  data-api="${API_BASE}"\n  defer></script>`;

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(snippet);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* ignore */
    }
  };

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
      <div className="space-y-6">
        <SectionCard title="Web widget" description="An embeddable chat bubble for any website.">
          <div className="grid gap-5 sm:grid-cols-2">
            <Field label="Accent color">
              <div className="flex items-center gap-2">
                <input
                  type="color"
                  value={w.primaryColor}
                  onChange={(e) => update((d) => void (d.widget.primaryColor = e.target.value))}
                  className="h-9 w-12 cursor-pointer rounded-md border border-border bg-surface-2"
                />
                <Input
                  value={w.primaryColor}
                  onChange={(e) => update((d) => void (d.widget.primaryColor = e.target.value))}
                  className="font-mono"
                />
              </div>
            </Field>
            <Field label="Launcher text">
              <Input
                value={w.launcherText}
                onChange={(e) => update((d) => void (d.widget.launcherText = e.target.value))}
              />
            </Field>
            <Field label="Position">
              <select
                value={w.position}
                onChange={(e) =>
                  update((d) => void (d.widget.position = e.target.value as "bottom-right" | "bottom-left"))
                }
                className="h-9 w-full rounded-md border border-border bg-surface-2 px-2 text-sm text-text"
              >
                <option value="bottom-right">Bottom right</option>
                <option value="bottom-left">Bottom left</option>
              </select>
            </Field>
            <Field label="Theme">
              <select
                value={w.mode}
                onChange={(e) => update((d) => void (d.widget.mode = e.target.value as "dark" | "light"))}
                className="h-9 w-full rounded-md border border-border bg-surface-2 px-2 text-sm text-text"
              >
                <option value="dark">Dark</option>
                <option value="light">Light</option>
              </select>
            </Field>
          </div>
          <div className="flex items-center gap-3 rounded-md border border-border bg-surface-2/50 p-3">
            <div className="flex-1">
              <div className="text-sm font-medium text-text">“Powered by BotForge” badge</div>
              <div className="text-xs text-muted">Show a small attribution in the widget footer.</div>
            </div>
            <Switch checked={w.branding} onCheckedChange={(v) => update((d) => void (d.widget.branding = v))} />
          </div>
        </SectionCard>

        <SectionCard title="Embed snippet" description="Paste this before </body> on any page.">
          <div className="relative">
            <pre className="overflow-x-auto rounded-md border border-border bg-surface-2/60 p-3 font-mono text-xs text-muted">
              {snippet}
            </pre>
            <button
              onClick={copy}
              className="absolute right-2 top-2 flex items-center gap-1 rounded-md border border-border bg-surface px-2 py-1 text-xs text-muted transition-colors hover:text-text"
            >
              {copied ? <Check className="size-3.5 text-success" /> : <Copy className="size-3.5" />}
              {copied ? "Copied" : "Copy"}
            </button>
          </div>
          <p className="text-xs text-faint">
            The widget loads its theme, welcome message, and quick replies from this agent’s public config.
          </p>
        </SectionCard>
      </div>

      {/* Live preview */}
      <div>
        <div className="sticky top-32 rounded-lg border border-border bg-surface p-4">
          <div className="mb-3 text-xs font-medium uppercase tracking-wide text-faint">Live preview</div>
          <WidgetPreview
            name={draft.persona.displayName || draft.name}
            welcome={draft.persona.welcomeMessage}
            prompts={draft.persona.suggestedPrompts}
            primaryColor={w.primaryColor}
            launcherText={w.launcherText}
            branding={w.branding}
            mode={w.mode}
            position={w.position}
          />
        </div>
      </div>
    </div>
  );
}

function WidgetPreview({
  name,
  welcome,
  prompts,
  primaryColor,
  launcherText,
  branding,
  mode,
  position,
}: {
  name: string;
  welcome: string;
  prompts: string[];
  primaryColor: string;
  launcherText: string;
  branding: boolean;
  mode: "dark" | "light";
  position: "bottom-right" | "bottom-left";
}) {
  const dark = mode !== "light";
  const bg = dark ? "#16181D" : "#FFFFFF";
  const bg2 = dark ? "#1E2127" : "#F4F5F7";
  const text = dark ? "#E7E9EE" : "#14161A";
  const border = dark ? "#2A2E37" : "#E3E6EA";
  const alignEnd = position === "bottom-right";

  return (
    <div className="space-y-3">
      <div
        className="overflow-hidden rounded-xl border shadow-lg"
        style={{ background: bg, borderColor: border, color: text }}
      >
        <div
          className="flex items-center gap-2 px-3 py-2.5 text-sm font-semibold text-white"
          style={{ background: primaryColor }}
        >
          <MessageSquare className="size-4" />
          {name || "Assistant"}
        </div>
        <div className="space-y-2 p-3">
          <div
            className="max-w-[85%] rounded-lg border px-3 py-2 text-xs"
            style={{ background: bg2, borderColor: border }}
          >
            {welcome || "Hi! How can I help you today?"}
          </div>
          <div className="flex flex-wrap gap-1.5">
            {(prompts ?? []).slice(0, 3).map((p, i) => (
              <span
                key={i}
                className="rounded-full border px-2 py-1 text-[11px]"
                style={{ background: bg2, borderColor: border }}
              >
                {p}
              </span>
            ))}
          </div>
        </div>
        {branding && (
          <div
            className="border-t px-3 py-1.5 text-center text-[10px]"
            style={{ borderColor: border, color: dark ? "#9AA0AB" : "#5A616B" }}
          >
            Powered by BotForge
          </div>
        )}
      </div>
      <div className={`flex ${alignEnd ? "justify-end" : "justify-start"}`}>
        <span
          className="inline-flex items-center gap-2 rounded-full px-4 py-2.5 text-sm font-semibold text-white shadow-lg"
          style={{ background: primaryColor }}
        >
          <MessageSquare className="size-4" /> {launcherText}
        </span>
      </div>
    </div>
  );
}
