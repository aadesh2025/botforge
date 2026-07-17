import Link from "next/link";
import { ArrowUpRight } from "lucide-react";
import type { Conversation } from "@/lib/mock/types";
import { Badge } from "@/components/ui/badge";
import { ChannelIcon } from "@/components/shared/channel-icon";
import { convoStatusMeta } from "@/lib/display";
import { relativeTime } from "@/lib/utils";

export function ConversationsPanel({ conversations }: { conversations: Conversation[] }) {
  return (
    <div className="flex h-full flex-col rounded-lg border border-border bg-surface">
      <div className="flex items-center justify-between border-b border-border p-5">
        <div>
          <h3 className="font-display text-base font-semibold text-text">Recent conversations</h3>
          <p className="text-sm text-muted">Live across every channel</p>
        </div>
        <Link
          href="/inbox"
          className="inline-flex items-center gap-1 text-sm font-medium text-ember-soft hover:text-ember"
        >
          Inbox <ArrowUpRight className="size-3.5" />
        </Link>
      </div>
      <ul className="flex-1 divide-y divide-border">
        {conversations.map((c) => {
          const status = convoStatusMeta[c.status];
          return (
            <li key={c.id}>
              <Link
                href={`/inbox/${c.id}`}
                className="flex flex-col gap-1.5 px-5 py-3.5 transition-colors hover:bg-surface-2/50"
              >
                <div className="flex items-center gap-2">
                  <span className="grid size-5 shrink-0 place-items-center rounded border border-border bg-surface-2 text-faint">
                    <ChannelIcon channel={c.channel} />
                  </span>
                  <span className="truncate font-mono text-xs text-muted">{c.visitor}</span>
                  <Badge variant={status.variant} className="ml-auto shrink-0">
                    {status.label}
                  </Badge>
                </div>
                <p className="line-clamp-1 text-sm text-text">{c.preview}</p>
                <div className="flex items-center gap-2 text-[11px] text-faint">
                  <span>{c.agentName}</span>
                  <span className="text-border-strong">·</span>
                  <span>{c.messages} messages</span>
                  <span className="text-border-strong">·</span>
                  <span>{relativeTime(c.updatedAt)}</span>
                </div>
              </Link>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
