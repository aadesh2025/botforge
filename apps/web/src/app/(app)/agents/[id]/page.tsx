"use client";

import { useEffect, useRef, useState } from "react";
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
import { getAgent, listVersions, patchVersion } from "@/lib/api/agents";
import { draftToPatch, versionToDraft } from "@/lib/api/agent-mapping";
import { useSession } from "@/lib/store/session";

const TABS = ["persona", "model", "knowledge", "tools", "channels", "versions", "settings"] as const;
type Tab = (typeof TABS)[number];

export default function AgentBuilderPage({ params }: { params: { id: string } }) {
  const activeOrgId = useSession((s) => s.activeOrgId);
  const { draft, agentId, versionNumber, init, dirty, beginSave, markSaved, retarget } = useBuilder();
  const [tab, setTab] = useState<Tab>("persona");
  const loadedFor = useRef<string | null>(null);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["agent", params.id, activeOrgId],
    queryFn: async () => {
      const [agent, versions] = await Promise.all([getAgent(params.id), listVersions(params.id)]);
      const latest = versions.reduce((a, b) => (b.version > a.version ? b : a), versions[0]);
      return { agent, latest };
    },
    enabled: Boolean(activeOrgId),
  });

  // Seed the builder store once the agent loads.
  useEffect(() => {
    if (data && loadedFor.current !== params.id) {
      loadedFor.current = params.id;
      init(versionToDraft(data.agent, data.latest), data.agent.id, data.latest.version, data.latest.is_published);
    }
  }, [data, params.id, init]);

  // Restore the active tab from the URL on mount.
  useEffect(() => {
    const t = new URLSearchParams(window.location.search).get("tab");
    if (t && (TABS as readonly string[]).includes(t)) setTab(t as Tab);
  }, []);

  // Debounced autosave: PATCH the draft version whenever it becomes dirty.
  useEffect(() => {
    if (!dirty || !draft || !agentId || versionNumber === null) return;
    const timer = setTimeout(async () => {
      beginSave();
      try {
        const saved = await patchVersion(agentId, versionNumber, draftToPatch(draft));
        // Branch-on-edit: if the backend forked a new draft off a published version, the
        // returned version number is higher — re-point the builder at that new draft.
        if (saved.version !== versionNumber) retarget(saved.version);
      } finally {
        markSaved();
      }
    }, 800);
    return () => clearTimeout(timer);
  }, [dirty, draft, agentId, versionNumber, beginSave, markSaved, retarget]);

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

      <div className="grid gap-6 pt-6 xl:grid-cols-3">
        <div className="min-w-0 xl:col-span-2">
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

        <div className="xl:col-span-1">
          <div className="sticky top-32">
            <Playground />
          </div>
        </div>
      </div>
    </div>
  );
}
