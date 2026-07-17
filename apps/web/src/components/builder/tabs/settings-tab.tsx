"use client";

import { Copy, Trash2 } from "lucide-react";
import { Field, SectionCard } from "@/components/builder/field";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { useBuilder } from "@/lib/store/builder";

export function SettingsTab() {
  const draft = useBuilder((s) => s.draft);
  const update = useBuilder((s) => s.update);
  if (!draft) return null;

  return (
    <div className="space-y-6">
      <SectionCard title="General" description="Basic details for this agent.">
        <div className="grid gap-5 sm:grid-cols-2">
          <Field label="Agent name" htmlFor="agentName">
            <Input
              id="agentName"
              value={draft.name}
              onChange={(e) => update((d) => void (d.name = e.target.value))}
            />
          </Field>
          <Field label="Agent ID">
            <Input value={draft.id} readOnly className="font-mono text-muted" />
          </Field>
        </div>
      </SectionCard>

      <SectionCard title="Duplicate" description="Clone this agent's full configuration into a new draft.">
        <Button variant="outline" size="sm">
          <Copy /> Duplicate agent
        </Button>
      </SectionCard>

      <section className="rounded-lg border border-error/30 bg-error/[0.04]">
        <div className="border-b border-error/20 p-5">
          <h3 className="font-display text-base font-semibold text-error">Danger zone</h3>
          <p className="mt-0.5 text-sm text-muted">
            Deleting an agent removes its versions, conversations, and channel connections. This cannot be
            undone.
          </p>
        </div>
        <div className="p-5">
          <Button variant="destructive" size="sm">
            <Trash2 /> Delete agent
          </Button>
        </div>
      </section>
    </div>
  );
}
