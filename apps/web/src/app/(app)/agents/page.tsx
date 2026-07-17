import Link from "next/link";
import { Bot, Plus } from "lucide-react";
import { PageHeader } from "@/components/dashboard/page-header";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ChannelIcon } from "@/components/shared/channel-icon";
import { agents } from "@/lib/mock/data";
import { agentStatusMeta, providerLabel } from "@/lib/display";
import { compact, relativeTime } from "@/lib/utils";

export default function AgentsPage() {
  return (
    <div className="mx-auto max-w-[1400px] space-y-6">
      <PageHeader title="Agents" description="Build, configure, and publish your AI agents.">
        <Button variant="primary">
          <Plus /> New agent
        </Button>
      </PageHeader>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {agents.map((agent) => {
          const status = agentStatusMeta[agent.status];
          return (
            <Link
              key={agent.id}
              href={`/agents/${agent.id}`}
              className="group relative overflow-hidden rounded-lg border border-border bg-surface p-5 transition-colors hover:border-border-strong"
            >
              <span className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-ember/70 to-transparent opacity-0 transition-opacity group-hover:opacity-100" />
              <div className="flex items-start justify-between">
                <span className="grid size-11 place-items-center rounded-lg border border-border bg-surface-2 font-display text-lg font-semibold text-muted">
                  {agent.name[0]}
                </span>
                <Badge variant={status.variant}>
                  {agent.status === "live" && <span className="size-1.5 rounded-full bg-success" />}
                  {status.label}
                </Badge>
              </div>
              <h3 className="mt-4 font-display text-lg font-semibold text-text">{agent.name}</h3>
              <div className="mt-1 flex items-center gap-2 text-xs text-faint">
                <span className="font-mono">{providerLabel[agent.provider]}</span>
                <span className="text-border-strong">·</span>
                <span className="truncate font-mono">{agent.model}</span>
              </div>

              <div className="mt-4 flex items-center gap-1.5">
                {agent.channels.map((c) => (
                  <span key={c} className="grid size-6 place-items-center rounded border border-border bg-surface-2 text-faint">
                    <ChannelIcon channel={c} />
                  </span>
                ))}
              </div>

              <div className="mt-4 flex items-center justify-between border-t border-border pt-4 text-sm">
                <div>
                  <div className="font-semibold text-text">{compact(agent.conversations7d)}</div>
                  <div className="text-[11px] text-faint">conversations · 7d</div>
                </div>
                <div className="text-right">
                  <div className="font-semibold text-text">
                    {agent.resolutionRate ? `${Math.round(agent.resolutionRate * 100)}%` : "—"}
                  </div>
                  <div className="text-[11px] text-faint">resolved</div>
                </div>
                <div className="text-right">
                  <div className="font-semibold text-muted">{relativeTime(agent.updatedAt)}</div>
                  <div className="text-[11px] text-faint">updated</div>
                </div>
              </div>
            </Link>
          );
        })}

        {/* Create card */}
        <button className="flex min-h-[220px] flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-border-strong bg-surface/40 text-muted transition-colors hover:border-ember/40 hover:bg-ember/[0.03] hover:text-ember-soft">
          <span className="grid size-11 place-items-center rounded-lg border border-border bg-surface-2">
            <Bot className="size-5" />
          </span>
          <span className="text-sm font-medium">Create a new agent</span>
        </button>
      </div>
    </div>
  );
}
