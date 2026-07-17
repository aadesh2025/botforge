"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowLeft, Check, Cloud, Loader2, Rocket } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useBuilder } from "@/lib/store/builder";
import { publishVersion } from "@/lib/api/agents";
import { agentStatusMeta } from "@/lib/display";
import { relativeTime } from "@/lib/utils";

export function BuilderHeader() {
  const { draft, agentId, versionNumber, published, dirty, saving, lastSavedAt, setPublished } = useBuilder();
  const [publishing, setPublishing] = useState(false);
  if (!draft) return null;
  const status = agentStatusMeta[draft.status];

  async function onPublish() {
    if (!agentId || versionNumber === null) return;
    setPublishing(true);
    try {
      await publishVersion(agentId, versionNumber);
      setPublished(true);
    } finally {
      setPublishing(false);
    }
  }

  return (
    <div className="sticky top-14 z-20 -mx-4 border-b border-border bg-bg/85 px-4 py-3 backdrop-blur-md md:-mx-6 md:px-6 lg:-mx-8 lg:px-8">
      <div className="flex flex-wrap items-center gap-3">
        <Link
          href="/agents"
          className="grid size-8 place-items-center rounded-md border border-border bg-surface text-muted transition-colors hover:text-text"
          aria-label="Back to agents"
        >
          <ArrowLeft className="size-4" />
        </Link>
        <span className="grid size-9 place-items-center rounded-md bg-gradient-to-br from-ember to-ember-2 font-display text-sm font-bold text-[#0A0B0D]">
          {draft.name[0]}
        </span>
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h1 className="truncate font-display text-lg font-semibold text-text">{draft.name}</h1>
            <Badge variant={status.variant}>
              {draft.status === "live" && <span className="size-1.5 rounded-full bg-success" />}
              {status.label}
            </Badge>
          </div>
          <p className="font-mono text-[11px] text-faint">{draft.id}</p>
        </div>

        <div className="ml-auto flex items-center gap-3">
          <SaveIndicator dirty={dirty} saving={saving} lastSavedAt={lastSavedAt} />
          {published && !dirty ? (
            <Badge variant="success">
              <Check className="size-3" /> Published
            </Badge>
          ) : (
            <Button variant="primary" size="sm" onClick={onPublish} disabled={publishing || dirty}>
              {publishing ? <Loader2 className="size-4 animate-spin" /> : <Rocket className="size-4" />} Publish
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

function SaveIndicator({
  dirty,
  saving,
  lastSavedAt,
}: {
  dirty: boolean;
  saving: boolean;
  lastSavedAt: number | null;
}) {
  if (saving) {
    return (
      <span className="flex items-center gap-1.5 text-xs text-muted">
        <Loader2 className="size-3.5 animate-spin text-ember-soft" /> Saving…
      </span>
    );
  }
  if (dirty) {
    return (
      <span className="flex items-center gap-1.5 text-xs text-warn">
        <Cloud className="size-3.5" /> Unsaved changes
      </span>
    );
  }
  return (
    <span className="flex items-center gap-1.5 text-xs text-faint">
      <Check className="size-3.5 text-success" />
      Saved{lastSavedAt ? ` ${relativeTime(new Date(lastSavedAt).toISOString())}` : ""}
    </span>
  );
}
