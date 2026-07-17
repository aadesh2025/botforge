import Link from "next/link";
import { ArrowUpRight } from "lucide-react";
import type { Agent } from "@/lib/mock/types";
import { Badge } from "@/components/ui/badge";
import { ChannelIcon } from "@/components/shared/channel-icon";
import { agentStatusMeta, providerLabel } from "@/lib/display";
import { compact } from "@/lib/utils";

export function AgentsPanel({ agents }: { agents: Agent[] }) {
  return (
    <div className="rounded-lg border border-border bg-surface">
      <div className="flex items-center justify-between border-b border-border p-5">
        <div>
          <h3 className="font-display text-base font-semibold text-text">Your agents</h3>
          <p className="text-sm text-muted">{agents.length} total</p>
        </div>
        <Link
          href="/agents"
          className="inline-flex items-center gap-1 text-sm font-medium text-ember-soft hover:text-ember"
        >
          View all <ArrowUpRight className="size-3.5" />
        </Link>
      </div>
      <ul className="divide-y divide-border">
        {agents.map((agent) => {
          const status = agentStatusMeta[agent.status];
          return (
            <li key={agent.id}>
              <Link
                href={`/agents/${agent.id}`}
                className="group flex items-center gap-4 px-5 py-3.5 transition-colors hover:bg-surface-2/50"
              >
                <span className="grid size-9 shrink-0 place-items-center rounded-md border border-border bg-surface-2 font-display text-sm font-semibold text-muted">
                  {agent.name[0]}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="truncate text-sm font-medium text-text">{agent.name}</span>
                    <Badge variant={status.variant}>
                      {agent.status === "live" && (
                        <span className="size-1.5 rounded-full bg-success" />
                      )}
                      {status.label}
                    </Badge>
                  </div>
                  <div className="mt-0.5 flex items-center gap-2 text-xs text-faint">
                    <span className="font-mono">{providerLabel[agent.provider]}</span>
                    <span className="text-border-strong">·</span>
                    <span className="truncate font-mono">{agent.model}</span>
                  </div>
                </div>
                <div className="hidden items-center gap-1 text-faint sm:flex">
                  {agent.channels.map((c) => (
                    <span
                      key={c}
                      className="grid size-6 place-items-center rounded border border-border bg-surface-2"
                    >
                      <ChannelIcon channel={c} />
                    </span>
                  ))}
                </div>
                <div className="w-16 text-right">
                  <div className="text-sm font-semibold text-text">{compact(agent.conversations7d)}</div>
                  <div className="text-[11px] text-faint">7d chats</div>
                </div>
              </Link>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
