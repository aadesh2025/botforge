"use client";

import { useState } from "react";
import { Plus, Wrench, Globe, Workflow, Zap } from "lucide-react";
import { SectionCard } from "@/components/builder/field";
import { Switch } from "@/components/ui/switch";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { tools as seedTools, type ToolRef } from "@/lib/mock/builder";

const kindMeta = {
  builtin: { label: "Built-in", icon: Zap },
  http: { label: "HTTP", icon: Globe },
  n8n: { label: "n8n", icon: Workflow },
} as const;

export function ToolsTab() {
  const [tools, setTools] = useState<ToolRef[]>(seedTools);
  const toggle = (id: string) =>
    setTools((prev) => prev.map((t) => (t.id === id ? { ...t, enabled: !t.enabled } : t)));

  const groups: ToolRef["kind"][] = ["builtin", "http", "n8n"];

  return (
    <div className="space-y-6">
      {groups.map((kind) => {
        const list = tools.filter((t) => t.kind === kind);
        const Meta = kindMeta[kind];
        return (
          <SectionCard
            key={kind}
            title={`${Meta.label} tools`}
            description={
              kind === "builtin"
                ? "Ready-made capabilities you can switch on."
                : kind === "http"
                  ? "Call your own APIs with a guarded HTTP request."
                  : "Bind local n8n workflows as callable tools."
            }
          >
            <ul className="space-y-2">
              {list.map((t) => (
                <li key={t.id} className="flex items-center gap-3 rounded-md border border-border bg-surface-2/50 p-3">
                  <span className="grid size-8 place-items-center rounded-md border border-border bg-surface-2 text-ember-soft">
                    <Meta.icon className="size-4" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-sm text-text">{t.name}</span>
                      {t.enabled && <Badge variant="success">on</Badge>}
                    </div>
                    <div className="truncate text-xs text-muted">{t.description}</div>
                  </div>
                  <Switch checked={t.enabled} onCheckedChange={() => toggle(t.id)} />
                </li>
              ))}
            </ul>
            {kind !== "builtin" && (
              <Button variant="outline" size="sm">
                <Plus /> {kind === "http" ? "New HTTP tool" : "Bind n8n workflow"}
              </Button>
            )}
          </SectionCard>
        );
      })}

      <div className="flex items-center gap-3 rounded-lg border border-border bg-surface-2/40 p-4 text-sm text-muted">
        <Wrench className="size-4 shrink-0 text-faint" />
        Tools run inside an iteration-capped loop. Every call is logged to{" "}
        <span className="font-mono text-ember-soft">tool_runs</span> with inputs, outputs, and latency.
      </div>
    </div>
  );
}
