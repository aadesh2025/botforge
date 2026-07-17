import { Clock, ExternalLink, Webhook, Workflow as WorkflowIcon, Zap } from "lucide-react";
import { PageHeader } from "@/components/dashboard/page-header";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { workflows } from "@/lib/mock/automations";
import { relativeTime } from "@/lib/utils";

const triggerIcon = { webhook: Webhook, schedule: Clock, manual: Zap } as const;

export default function AutomationsPage() {
  return (
    <div className="mx-auto max-w-[1200px] space-y-6">
      <PageHeader title="Automations" description="n8n workflows your agents can trigger as tools.">
        <Button variant="outline" size="default">
          <ExternalLink /> Open n8n
        </Button>
        <Button variant="primary" size="default">
          Bind workflow
        </Button>
      </PageHeader>

      <div className="flex items-center gap-3 rounded-lg border border-success/25 bg-success/[0.05] px-4 py-3 text-sm">
        <span className="grid size-8 place-items-center rounded-md border border-success/30 bg-success/10 text-success">
          <WorkflowIcon className="size-4" />
        </span>
        <div className="flex-1">
          <span className="font-medium text-text">n8n connected</span>
          <span className="text-muted"> · http://localhost:5678 · {workflows.length} workflows synced</span>
        </div>
        <Badge variant="success">
          <span className="size-1.5 rounded-full bg-success" /> Online
        </Badge>
      </div>

      <div className="overflow-hidden rounded-lg border border-border bg-surface">
        <ul className="divide-y divide-border">
          {workflows.map((wf) => {
            const TIcon = triggerIcon[wf.trigger];
            return (
              <li key={wf.id} className="flex items-center gap-4 px-5 py-4 transition-colors hover:bg-surface-2/40">
                <span className="grid size-10 shrink-0 place-items-center rounded-md border border-border bg-surface-2 text-ember-soft">
                  <TIcon className="size-4" />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="truncate font-medium text-text">{wf.name}</span>
                    <Badge variant={wf.active ? "success" : "default"}>{wf.active ? "Active" : "Inactive"}</Badge>
                  </div>
                  <div className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-faint">
                    <span className="font-mono capitalize">{wf.trigger}</span>
                    <span className="text-border-strong">·</span>
                    <span>{wf.nodes} nodes</span>
                    {wf.lastRun && (
                      <>
                        <span className="text-border-strong">·</span>
                        <span>ran {relativeTime(wf.lastRun)}</span>
                      </>
                    )}
                  </div>
                </div>
                <div className="hidden items-center gap-1.5 md:flex">
                  {wf.boundAgents.length ? (
                    wf.boundAgents.map((a) => (
                      <span key={a} className="rounded-md border border-ember/25 bg-ember/[0.07] px-2 py-0.5 text-xs text-ember-soft">
                        {a}
                      </span>
                    ))
                  ) : (
                    <span className="text-xs text-faint">Not bound</span>
                  )}
                </div>
                <Button variant="outline" size="sm">
                  Bind as tool
                </Button>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
