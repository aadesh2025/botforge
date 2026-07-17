"use client";

import { useState } from "react";
import { CornerDownLeft, Hand, Tag, UserPlus, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ChannelIcon } from "@/components/shared/channel-icon";
import { convoStatusMeta } from "@/lib/display";
import { inboxThreads, type MsgRole } from "@/lib/mock/inbox";
import { cn, relativeTime } from "@/lib/utils";

const filters = ["all", "open", "handoff", "closed"] as const;
type Filter = (typeof filters)[number];

const roleMeta: Record<MsgRole, { align: string; bubble: string; label: string }> = {
  visitor: { align: "justify-start", bubble: "border border-border bg-surface-2 text-text", label: "Visitor" },
  agent: { align: "justify-start", bubble: "border border-ember/25 bg-ember/[0.07] text-text", label: "Ava (bot)" },
  operator: { align: "justify-end", bubble: "bg-ember text-[#0A0B0D]", label: "You" },
};

export function InboxView({ initialId }: { initialId?: string }) {
  const [filter, setFilter] = useState<Filter>("all");
  const [selectedId, setSelectedId] = useState(initialId ?? inboxThreads[0].id);
  const [draft, setDraft] = useState("");

  const list = inboxThreads.filter((t) => filter === "all" || t.status === filter);
  const thread = inboxThreads.find((t) => t.id === selectedId) ?? inboxThreads[0];
  // A human is handling only once someone is assigned; otherwise the bot owns it
  // (including a handoff that's been requested but not yet taken over).
  const isBot = thread.assignee === null;

  return (
    <div className="flex h-[calc(100vh-6.5rem)] overflow-hidden rounded-lg border border-border bg-surface">
      {/* List pane */}
      <div className="flex w-full max-w-[340px] flex-col border-r border-border">
        <div className="flex items-center gap-1 border-b border-border p-2">
          {filters.map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={cn(
                "flex-1 rounded-md px-2 py-1.5 text-xs font-medium capitalize transition-colors",
                filter === f ? "bg-surface-2 text-text" : "text-muted hover:text-text",
              )}
            >
              {f}
            </button>
          ))}
        </div>
        <div className="flex-1 overflow-y-auto scroll-thin">
          {list.map((t) => {
            const status = convoStatusMeta[t.status];
            const active = t.id === selectedId;
            return (
              <button
                key={t.id}
                onClick={() => setSelectedId(t.id)}
                className={cn(
                  "flex w-full flex-col gap-1.5 border-b border-border px-4 py-3 text-left transition-colors",
                  active ? "bg-surface-2" : "hover:bg-surface-2/50",
                )}
              >
                <div className="flex items-center gap-2">
                  <span className="grid size-5 place-items-center rounded border border-border bg-surface-2 text-faint">
                    <ChannelIcon channel={t.channel} />
                  </span>
                  <span className="truncate font-mono text-xs text-muted">{t.visitor}</span>
                  {t.unread && <span className="ml-auto size-2 rounded-full bg-ember" />}
                </div>
                <p className="line-clamp-1 text-sm text-text">{t.messages[t.messages.length - 1].text}</p>
                <div className="flex items-center gap-2">
                  <Badge variant={status.variant}>{status.label}</Badge>
                  <span className="text-[11px] text-faint">{relativeTime(t.updatedAt)}</span>
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* Thread pane */}
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center gap-3 border-b border-border px-5 py-3">
          <span className="grid size-9 place-items-center rounded-md border border-border bg-surface-2 text-muted">
            <ChannelIcon channel={thread.channel} />
          </span>
          <div className="min-w-0 flex-1">
            <div className="truncate font-medium text-text">{thread.visitor}</div>
            <div className="text-xs text-faint">
              {thread.agentName}
              {thread.assignee ? ` · assigned to ${thread.assignee}` : ""}
            </div>
          </div>
          <div className="hidden items-center gap-1.5 sm:flex">
            {thread.tags.map((tag) => (
              <span key={tag} className="inline-flex items-center gap-1 rounded-md border border-border bg-surface-2 px-2 py-0.5 text-xs text-muted">
                <Tag className="size-3" /> {tag}
              </span>
            ))}
          </div>
        </div>

        <div className="flex-1 space-y-3 overflow-y-auto p-5 scroll-thin">
          {thread.messages.map((m) => {
            const meta = roleMeta[m.role];
            return (
              <div key={m.id} className={cn("flex", meta.align)}>
                <div className="max-w-[75%]">
                  <div className={cn("rounded-2xl px-3.5 py-2 text-sm leading-relaxed", meta.bubble)}>{m.text}</div>
                  <div className={cn("mt-1 text-[11px] text-faint", m.role === "operator" ? "text-right" : "")}>
                    {meta.label} · {relativeTime(m.at)}
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        {/* Operator controls */}
        <div className="border-t border-border p-3">
          <div className="mb-2 flex items-center gap-2">
            {isBot ? (
              <Button variant="primary" size="sm">
                <Hand className="size-3.5" /> Take over
              </Button>
            ) : (
              <Button variant="outline" size="sm">
                <X className="size-3.5" /> Hand back to bot
              </Button>
            )}
            <Button variant="ghost" size="sm">
              <UserPlus className="size-3.5" /> Assign
            </Button>
            <span className="ml-auto text-[11px] text-faint">
              {isBot ? "Bot is handling this conversation" : "You are handling this conversation"}
            </span>
          </div>
          <div className="flex items-end gap-2 rounded-lg border border-border bg-surface-2 p-2 focus-within:border-ember/50">
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              rows={1}
              placeholder={isBot ? "Take over to reply…" : "Type a reply…"}
              disabled={isBot}
              className="max-h-28 flex-1 resize-none bg-transparent px-1 py-1.5 text-sm text-text placeholder:text-faint focus:outline-none disabled:opacity-60"
            />
            <button
              disabled={isBot || !draft.trim()}
              className={cn(
                "grid size-8 shrink-0 place-items-center rounded-md transition-colors",
                !isBot && draft.trim() ? "bg-ember text-[#0A0B0D] hover:bg-ember-2" : "bg-surface-3 text-faint",
              )}
              aria-label="Send reply"
            >
              <CornerDownLeft className="size-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
