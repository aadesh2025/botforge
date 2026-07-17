"use client";

import { useEffect, useState } from "react";
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
import { makeDraft } from "@/lib/mock/builder";

const TABS = ["persona", "model", "knowledge", "tools", "channels", "versions", "settings"] as const;
type Tab = (typeof TABS)[number];

export default function AgentBuilderPage({ params }: { params: { id: string } }) {
  const { draft, init, dirty, beginSave, markSaved } = useBuilder();
  const [tab, setTab] = useState<Tab>("persona");

  // Seed the draft store for this agent id.
  useEffect(() => {
    init(makeDraft(params.id));
  }, [params.id, init]);

  // Restore the active tab from the URL on mount.
  useEffect(() => {
    const t = new URLSearchParams(window.location.search).get("tab");
    if (t && (TABS as readonly string[]).includes(t)) setTab(t as Tab);
  }, []);

  // Debounced autosave whenever the draft becomes dirty.
  useEffect(() => {
    if (!dirty) return;
    const save = setTimeout(() => {
      beginSave();
      setTimeout(markSaved, 480);
    }, 850);
    return () => clearTimeout(save);
  }, [dirty, draft, beginSave, markSaved]);

  const onTabChange = (v: string) => {
    setTab(v as Tab);
    const url = new URL(window.location.href);
    url.searchParams.set("tab", v);
    window.history.replaceState(null, "", url.toString());
  };

  if (!draft) return null;

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
