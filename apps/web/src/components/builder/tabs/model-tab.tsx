"use client";

import { BookOpen, Wrench, Brain, Plus, UserRound, X } from "lucide-react";
import { Field, SectionCard, SliderField } from "@/components/builder/field";
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useBuilder } from "@/lib/store/builder";
import { credentialOptions, providerCatalog } from "@/lib/mock/builder";
import type { Provider } from "@/lib/mock/types";
import type { FeatureToggles } from "@/lib/mock/builder";

export function ModelTab() {
  const draft = useBuilder((s) => s.draft);
  const update = useBuilder((s) => s.update);
  if (!draft) return null;
  const m = draft.model;
  // First provider not already used as the primary or an existing fallback.
  const nextFallback = (Object.keys(providerCatalog) as Provider[]).find(
    (k) => k !== m.provider && !m.fallbacks.some((f) => f.provider === k),
  );
  const provider = providerCatalog[m.provider];

  return (
    <div className="space-y-6">
      <SectionCard title="Provider & model" description="Free-first: Groq is the fastest free default.">
        <div className="grid gap-5 sm:grid-cols-2">
          <Field label="Provider">
            <Select
              value={m.provider}
              onValueChange={(v) =>
                update((d) => {
                  d.model.provider = v as Provider;
                  d.model.model = providerCatalog[v as Provider].models[0];
                })
              }
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {(Object.keys(providerCatalog) as Provider[]).map((key) => (
                  <SelectItem key={key} value={key}>
                    {providerCatalog[key].label}
                    {providerCatalog[key].free ? "  · free" : ""}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <Field label="Model">
            <Select value={m.model} onValueChange={(v) => update((d) => void (d.model.model = v))}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {provider.models.map((model) => (
                  <SelectItem key={model} value={model}>
                    {model}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant={provider.free ? "success" : "warn"}>
            {provider.free ? "Free tier" : "Paid provider"}
          </Badge>
          {m.fallbacks.length > 0 ? (
            <Badge variant="default">
              Fallback: {m.fallbacks.map((f) => providerCatalog[f.provider].label).join(" → ")}
            </Badge>
          ) : null}
        </div>

        <Field
          label="Fallback providers"
          description="Tried in order if the primary fails before it starts replying. Not used once a reply has begun."
        >
          <div className="space-y-2">
            {m.fallbacks.map((f, i) => (
              <div key={`${f.provider}-${i}`} className="flex items-center gap-2">
                <Select
                  value={f.provider}
                  onValueChange={(v) =>
                    update((d) => {
                      d.model.fallbacks[i].provider = v as Provider;
                      d.model.fallbacks[i].model = providerCatalog[v as Provider].models[0];
                    })
                  }
                >
                  <SelectTrigger className="w-[190px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {(Object.keys(providerCatalog) as Provider[])
                      .filter((k) => k !== m.provider)
                      .map((key) => (
                        <SelectItem key={key} value={key}>
                          {providerCatalog[key].label}
                        </SelectItem>
                      ))}
                  </SelectContent>
                </Select>
                <Select
                  value={f.model}
                  onValueChange={(v) => update((d) => void (d.model.fallbacks[i].model = v))}
                >
                  <SelectTrigger className="flex-1">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {providerCatalog[f.provider].models.map((model) => (
                      <SelectItem key={model} value={model}>
                        {model}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Button
                  variant="ghost"
                  size="sm"
                  aria-label={`Remove ${providerCatalog[f.provider].label} fallback`}
                  onClick={() => update((d) => void d.model.fallbacks.splice(i, 1))}
                >
                  <X className="size-4" />
                </Button>
              </div>
            ))}
            <Button
              variant="outline"
              size="sm"
              disabled={nextFallback === undefined}
              onClick={() =>
                update((d) => {
                  if (nextFallback === undefined) return;
                  d.model.fallbacks.push({
                    provider: nextFallback,
                    model: providerCatalog[nextFallback].models[0],
                  });
                })
              }
            >
              <Plus className="size-4" /> Add fallback
            </Button>
            {m.fallbacks.length === 0 ? (
              <p className="text-xs text-faint">
                No fallback configured — if {provider.label} fails, the turn returns an error.
              </p>
            ) : null}
          </div>
        </Field>
        <Field label="Credentials" description="Use the org key, or bring your own for this agent.">
          <Select value={m.credential} onValueChange={(v) => update((d) => void (d.model.credential = v))}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {credentialOptions.map((c) => (
                <SelectItem key={c.value} value={c.value}>
                  {c.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
      </SectionCard>

      <SectionCard title="Sampling" description="Control creativity and length of responses.">
        <div className="grid gap-6 sm:grid-cols-2">
          <SliderField label="Temperature" value={m.temperature} display={m.temperature.toFixed(2)}>
            <Slider
              value={[m.temperature]}
              min={0}
              max={2}
              step={0.05}
              onValueChange={([v]) => update((d) => void (d.model.temperature = v))}
            />
          </SliderField>
          <SliderField label="Top P" value={m.topP} display={m.topP.toFixed(2)}>
            <Slider
              value={[m.topP]}
              min={0}
              max={1}
              step={0.05}
              onValueChange={([v]) => update((d) => void (d.model.topP = v))}
            />
          </SliderField>
          <SliderField label="Max tokens" value={m.maxTokens} display={String(m.maxTokens)}>
            <Slider
              value={[m.maxTokens]}
              min={256}
              max={8192}
              step={128}
              onValueChange={([v]) => update((d) => void (d.model.maxTokens = v))}
            />
          </SliderField>
          <SliderField label="Frequency penalty" value={m.frequencyPenalty} display={m.frequencyPenalty.toFixed(1)}>
            <Slider
              value={[m.frequencyPenalty]}
              min={0}
              max={2}
              step={0.1}
              onValueChange={([v]) => update((d) => void (d.model.frequencyPenalty = v))}
            />
          </SliderField>
        </div>
      </SectionCard>

      <SectionCard title="Capabilities" description="Toggle what this agent is allowed to do.">
        <FeatureRow
          icon={<BookOpen className="size-4" />}
          label="Knowledge retrieval (RAG)"
          desc="Ground answers in attached knowledge bases."
          k="rag"
        />
        <FeatureRow
          icon={<Wrench className="size-4" />}
          label="Tool calling"
          desc="Let the agent call tools and automations."
          k="tools"
        />
        <FeatureRow
          icon={<Brain className="size-4" />}
          label="Memory"
          desc="Remember earlier turns with long-term summaries."
          k="memory"
        />
        <FeatureRow
          icon={<UserRound className="size-4" />}
          label="Human handoff"
          desc="Escalate to a human operator when stuck."
          k="handoff"
        />
      </SectionCard>
    </div>
  );
}

function FeatureRow({
  icon,
  label,
  desc,
  k,
}: {
  icon: React.ReactNode;
  label: string;
  desc: string;
  k: keyof FeatureToggles;
}) {
  const draft = useBuilder((s) => s.draft);
  const update = useBuilder((s) => s.update);
  if (!draft) return null;
  return (
    <div className="flex items-center gap-3 rounded-md border border-border bg-surface-2/50 p-3">
      <span className="grid size-8 shrink-0 place-items-center rounded-md border border-border bg-surface-2 text-ember-soft">
        {icon}
      </span>
      <div className="min-w-0 flex-1">
        <div className="text-sm font-medium text-text">{label}</div>
        <div className="text-xs text-muted">{desc}</div>
      </div>
      <Switch
        checked={draft.features[k]}
        onCheckedChange={(v) => update((d) => void (d.features[k] = v))}
      />
    </div>
  );
}
