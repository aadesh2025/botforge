"use client";

import { GitBranch, RotateCcw, Rocket } from "lucide-react";
import { SectionCard } from "@/components/builder/field";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { versions } from "@/lib/mock/builder";
import { relativeTime } from "@/lib/utils";

export function VersionsTab() {
  return (
    <SectionCard title="Version history" description="Publish drafts, compare, and roll back safely.">
      <ol className="relative space-y-1 before:absolute before:left-[15px] before:top-2 before:h-[calc(100%-1rem)] before:w-px before:bg-border">
        {versions.map((v) => (
          <li key={v.version} className="relative flex gap-4 rounded-md p-2 transition-colors hover:bg-surface-2/40">
            <span
              className={
                "z-10 mt-0.5 grid size-8 shrink-0 place-items-center rounded-full border " +
                (v.current
                  ? "border-ember/40 bg-ember/15 text-ember-soft"
                  : v.publishedAt
                    ? "border-border bg-surface-2 text-muted"
                    : "border-warn/40 bg-warn/10 text-warn")
              }
            >
              <GitBranch className="size-4" />
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="text-sm font-semibold text-text">{v.label}</span>
                {v.current && <Badge variant="ember">Current</Badge>}
                {!v.publishedAt && <Badge variant="warn">Draft</Badge>}
              </div>
              <p className="text-sm text-muted">{v.note}</p>
              <p className="mt-0.5 text-xs text-faint">
                {v.publishedAt ? `Published ${relativeTime(v.publishedAt)}` : "Not published yet"}
              </p>
            </div>
            <div className="flex items-center gap-2">
              {!v.publishedAt && (
                <Button variant="primary" size="sm">
                  <Rocket className="size-3.5" /> Publish
                </Button>
              )}
              {v.publishedAt && !v.current && (
                <Button variant="outline" size="sm">
                  <RotateCcw className="size-3.5" /> Roll back
                </Button>
              )}
            </div>
          </li>
        ))}
      </ol>
    </SectionCard>
  );
}
