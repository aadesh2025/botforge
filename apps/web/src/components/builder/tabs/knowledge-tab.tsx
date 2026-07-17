"use client";

import { useState } from "react";
import { BookOpen, FileText, Search } from "lucide-react";
import { Field, SectionCard, SliderField } from "@/components/builder/field";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useBuilder } from "@/lib/store/builder";
import { knowledgeBases } from "@/lib/mock/builder";
import { compact } from "@/lib/utils";

export function KnowledgeTab() {
  const draft = useBuilder((s) => s.draft);
  const update = useBuilder((s) => s.update);
  const [query, setQuery] = useState("");
  const [tested, setTested] = useState(false);
  if (!draft) return null;
  const k = draft.knowledge;

  const toggleKb = (id: string) =>
    update((d) => {
      const set = new Set(d.knowledge.attachedKbIds);
      if (set.has(id)) set.delete(id);
      else set.add(id);
      d.knowledge.attachedKbIds = Array.from(set);
    });

  return (
    <div className="space-y-6">
      <SectionCard title="Attached knowledge bases" description="The agent retrieves context from these.">
        <ul className="space-y-2">
          {knowledgeBases.map((kb) => {
            const attached = k.attachedKbIds.includes(kb.id);
            return (
              <li
                key={kb.id}
                className="flex items-center gap-3 rounded-md border border-border bg-surface-2/50 p-3"
              >
                <span className="grid size-8 place-items-center rounded-md border border-border bg-surface-2 text-ember-soft">
                  <BookOpen className="size-4" />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium text-text">{kb.name}</div>
                  <div className="text-xs text-faint">
                    {kb.docs} docs · {compact(kb.chunks)} chunks
                  </div>
                </div>
                <Switch checked={attached} onCheckedChange={() => toggleKb(kb.id)} />
              </li>
            );
          })}
        </ul>
      </SectionCard>

      <SectionCard title="Retrieval settings" description="Tune how context is fetched per query.">
        <div className="grid gap-6 sm:grid-cols-2">
          <SliderField label="Top K" value={k.topK} display={String(k.topK)}>
            <Slider
              value={[k.topK]}
              min={1}
              max={12}
              step={1}
              onValueChange={([v]) => update((d) => void (d.knowledge.topK = v))}
            />
          </SliderField>
          <SliderField label="Score threshold" value={k.scoreThreshold} display={k.scoreThreshold.toFixed(2)}>
            <Slider
              value={[k.scoreThreshold]}
              min={0}
              max={1}
              step={0.01}
              onValueChange={([v]) => update((d) => void (d.knowledge.scoreThreshold = v))}
            />
          </SliderField>
        </div>
        <div className="flex items-center gap-3 rounded-md border border-border bg-surface-2/50 p-3">
          <div className="flex-1">
            <div className="text-sm font-medium text-text">Hybrid search</div>
            <div className="text-xs text-muted">Combine keyword + vector ranking (RRF).</div>
          </div>
          <Switch checked={k.hybrid} onCheckedChange={(v) => update((d) => void (d.knowledge.hybrid = v))} />
        </div>
      </SectionCard>

      <SectionCard title="Test retrieval" description="See which chunks a query would pull in.">
        <Field label="Query">
          <div className="flex gap-2">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-faint" />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="e.g. What is the return window?"
                className="h-9 w-full rounded-md border border-border bg-surface-2 pl-9 pr-3 text-sm text-text placeholder:text-faint focus-visible:border-ember/60 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ember/40"
              />
            </div>
            <Button variant="primary" size="default" onClick={() => setTested(true)} disabled={!query.trim()}>
              Test
            </Button>
          </div>
        </Field>
        {tested && (
          <div className="space-y-2">
            {[0.91, 0.84, 0.78].map((score, i) => (
              <div key={i} className="rounded-md border border-border bg-surface-2/40 p-3">
                <div className="mb-1.5 flex items-center gap-2">
                  <FileText className="size-3.5 text-faint" />
                  <span className="font-mono text-xs text-muted">returns-policy.pdf · p{i + 2}</span>
                  <Badge variant="ember" className="ml-auto">
                    {score.toFixed(2)}
                  </Badge>
                </div>
                <p className="text-xs leading-relaxed text-muted">
                  Items may be returned within 30 days of delivery for a full refund, provided they are
                  unused and in original packaging. Refunds are processed to the original payment method…
                </p>
              </div>
            ))}
          </div>
        )}
      </SectionCard>
    </div>
  );
}
