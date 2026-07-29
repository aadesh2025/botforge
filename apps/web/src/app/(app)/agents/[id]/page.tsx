"use client";

import { use, useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { BuilderHeader } from "@/components/builder/builder-header";
import { Playground } from "@/components/builder/playground";
import { PersonaTab } from "@/components/builder/tabs/persona-tab";
import { ModelTab } from "@/components/builder/tabs/model-tab";
import { KnowledgeTab } from "@/components/builder/tabs/knowledge-tab";
import { ToolsTab } from "@/components/builder/tabs/tools-tab";
import { ChannelsTab } from "@/components/builder/tabs/channels-tab";
import { VersionsTab } from "@/components/builder/tabs/versions-tab";
import { SettingsTab } from "@/components/builder/tabs/settings-tab";
import { useBuilder } from "@/lib/store/builder";
import { getAgent, getWidgetConfig, listVersions, patchVersion, patchWidgetConfig } from "@/lib/api/agents";
import { ApiError } from "@/lib/api/client";
import { draftToPatch, draftToWidgetConfig, versionToDraft } from "@/lib/api/agent-mapping";
import { useSession } from "@/lib/store/session";

const TABS = ["persona", "model", "knowledge", "tools", "channels", "versions", "settings"] as const;
type Tab = (typeof TABS)[number];

/** Validation failures name the offending field — surface it, since that's what to fix. */
function describeSaveError(e: unknown): string {
  if (e instanceof ApiError) {
    const detail = Array.isArray(e.details)
      ? (e.details as { field?: string; error?: string }[]).find((d) => d?.field || d?.error)
      : undefined;
    return detail?.field ? `${e.message} (${detail.field}: ${detail.error ?? "invalid"})` : e.message;
  }
  return e instanceof Error ? e.message : "Couldn't save your changes.";
}

export default function AgentBuilderPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const activeOrgId = useSession((s) => s.activeOrgId);
  const { draft, agentId, versionNumber, init, dirty, beginSave, markSaved, markSaveFailed, retarget } =
    useBuilder();
  const [tab, setTab] = useState<Tab>("persona");
  const loadedFor = useRef<string | null>(null);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["agent", id, activeOrgId],
    queryFn: async () => {
      const [agent, versions, widget] = await Promise.all([
        getAgent(id),
        listVersions(id),
        // Appearance lives outside the version, so it loads alongside rather than within.
        getWidgetConfig(id).catch(() => ({}) as Record<string, unknown>),
      ]);
      const latest = versions.reduce((a, b) => (b.version > a.version ? b : a), versions[0]);
      return { agent, latest, widget };
    },
    enabled: Boolean(activeOrgId),
  });

  // Seed the builder store once the agent loads.
  useEffect(() => {
    if (data && loadedFor.current !== id) {
      loadedFor.current = id;
      init(
        versionToDraft(data.agent, data.latest, data.widget),
        data.agent.id,
        data.latest.version,
        data.latest.is_published,
      );
    }
  }, [data, id, init]);

  // Restore the active tab from the URL on mount.
  useEffect(() => {
    const t = new URLSearchParams(window.location.search).get("tab");
    // One-time mount read of the URL (window is unavailable during SSR).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (t && (TABS as readonly string[]).includes(t)) setTab(t as Tab);
  }, []);

  // Debounced autosave: PATCH the draft version whenever it becomes dirty.
  useEffect(() => {
    if (!dirty || !draft || !agentId || versionNumber === null) return;
    const timer = setTimeout(async () => {
      beginSave();
      try {
        // Two writes, deliberately: appearance is live on save, everything else waits for
        // a publish. Sent together so one debounce covers both.
        const [saved] = await Promise.all([
          patchVersion(agentId, versionNumber, draftToPatch(draft)),
          patchWidgetConfig(agentId, draftToWidgetConfig(draft)),
        ]);
        // Branch-on-edit: if the backend forked a new draft off a published version, the
        // returned version number is higher — re-point the builder at that new draft.
        if (saved.version !== versionNumber) retarget(saved.version);
        markSaved();
      } catch (e) {
        // Never report a rejected PATCH as saved — the edit is still only in the browser.
        // The draft stays dirty so the indicator says so and the next edit retries.
        markSaveFailed(describeSaveError(e));
      }
    }, 800);
    return () => clearTimeout(timer);
  }, [dirty, draft, agentId, versionNumber, beginSave, markSaved, markSaveFailed, retarget]);

  const onTabChange = (v: string) => {
    setTab(v as Tab);
    const url = new URL(window.location.href);
    url.searchParams.set("tab", v);
    window.history.replaceState(null, "", url.toString());
  };

  if (isLoading || !draft) {
    return (
      <div className="flex h-[60vh] items-center justify-center text-muted">
        <Loader2 className="mr-2 size-5 animate-spin text-ember-soft" /> Loading agent…
      </div>
    );
  }
  if (isError) {
    return <div className="flex h-[60vh] items-center justify-center text-error">Couldn&apos;t load this agent.</div>;
  }

  return (
    <div className="mx-auto max-w-[1500px]">
      <BuilderHeader />

      {/* Channels has its own full-width visual preview and needs no chat-testing pane, so it
          renders full width and drops the Playground column. Other tabs keep the 2:1 split. */}
      <div className={`grid gap-6 pt-6 ${tab === "channels" ? "" : "xl:grid-cols-3"}`}>
        <div className={tab === "channels" ? "min-w-0" : "min-w-0 xl:col-span-2"}>
          <Tabs value={tab} onValueChange={onTabChange}>
            <TabsList className="mb-5 rounded-lg border border-border bg-surface p-1">
              {TABS.map((t) => (
                <TabsTrigger key={t} value={t} className="capitalize">
                  {t}
                </TabsTrigger>
              ))}
            </TabsList>

            <TabsContent value="persona">
              <PersonaTab />
            </TabsContent>
            <TabsContent value="model">
              <ModelTab />
            </TabsContent>
            <TabsContent value="knowledge">
              <KnowledgeTab />
            </TabsContent>
            <TabsContent value="tools">
              <ToolsTab />
            </TabsContent>
            <TabsContent value="channels">
              <ChannelsTab />
            </TabsContent>
            <TabsContent value="versions">
              <VersionsTab />
            </TabsContent>
            <TabsContent value="settings">
              <SettingsTab />
            </TabsContent>
          </Tabs>
        </div>

        {tab !== "channels" && (
          <div className="xl:col-span-1">
            <div className="sticky top-32">
              <Playground />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
