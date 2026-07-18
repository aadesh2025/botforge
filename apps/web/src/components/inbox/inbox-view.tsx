"use client";

import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, Check, Headphones, Loader2, Send, User, UserCog } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  closeConversation,
  getInboxDetail,
  handback,
  listInbox,
  openInboxSocket,
  replyInbox,
  takeover,
} from "@/lib/api/inbox";
import { useSession } from "@/lib/store/session";

const STATUS_FILTERS = [
  { key: "", label: "All" },
  { key: "handoff", label: "Handoff" },
  { key: "active", label: "Active" },
  { key: "closed", label: "Closed" },
];

const statusVariant: Record<string, "success" | "warn" | "default"> = {
  handoff: "warn",
  active: "success",
  closed: "default",
};

export function InboxView({ initialId }: { initialId?: string }) {
  const qc = useQueryClient();
  const activeOrgId = useSession((s) => s.activeOrgId);
  const [filter, setFilter] = useState("");
  const [activeCid, setActiveCid] = useState<string | null>(initialId ?? null);

  const { data: items, isLoading } = useQuery({
    queryKey: ["inbox", activeOrgId, filter],
    queryFn: () => listInbox(filter || undefined),
    enabled: Boolean(activeOrgId),
  });

  // Realtime: refresh the queue on inbox events.
  useEffect(() => {
    if (!activeOrgId) return;
    const ws = openInboxSocket();
    if (!ws) return;
    ws.onmessage = () => {
      qc.invalidateQueries({ queryKey: ["inbox", activeOrgId] });
      qc.invalidateQueries({ queryKey: ["inbox-detail"] });
    };
    return () => ws.close();
  }, [activeOrgId, qc]);

  return (
    <div className="grid h-[calc(100vh-220px)] grid-cols-[340px_1fr] overflow-hidden rounded-lg border border-border bg-surface">
      <div className="flex flex-col border-r border-border">
        <div className="flex gap-1 border-b border-border p-2">
          {STATUS_FILTERS.map((f) => (
            <button
              key={f.key}
              onClick={() => setFilter(f.key)}
              className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                filter === f.key ? "bg-ember/15 text-ember-soft" : "text-muted hover:bg-surface-2"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
        <div className="flex-1 overflow-y-auto scroll-thin">
          {isLoading && <Skeleton className="m-3 h-16" />}
          {!isLoading && (items ?? []).length === 0 && (
            <p className="p-6 text-center text-sm text-muted">Nothing in the inbox yet.</p>
          )}
          {(items ?? []).map((it) => (
            <button
              key={it.id}
              onClick={() => setActiveCid(it.id)}
              className={`flex w-full flex-col gap-1 border-b border-border p-3 text-left transition-colors hover:bg-surface-2/50 ${
                activeCid === it.id ? "bg-surface-2/60" : ""
              }`}
            >
              <div className="flex items-center gap-2">
                <span className="truncate text-sm font-medium text-text">{it.title || "Conversation"}</span>
                <Badge variant={statusVariant[it.status] ?? "default"} className="ml-auto shrink-0">
                  {it.status}
                </Badge>
              </div>
              <div className="flex items-center gap-2 text-xs text-faint">
                <span className="capitalize">{it.channel}</span>
                <span>·</span>
                <span>{it.message_count} msgs</span>
                {it.handoff && it.handoff.status !== "resolved" && (
                  <Badge variant="ember" className="ml-auto">
                    {it.handoff.assigned_to ? "assigned" : "needs agent"}
                  </Badge>
                )}
              </div>
            </button>
          ))}
        </div>
      </div>

      {activeCid ? (
        <Thread cid={activeCid} onChanged={() => qc.invalidateQueries({ queryKey: ["inbox", activeOrgId] })} />
      ) : (
        <div className="flex items-center justify-center text-sm text-muted">
          Select a conversation to view it.
        </div>
      )}
    </div>
  );
}

function Thread({ cid, onChanged }: { cid: string; onChanged: () => void }) {
  const qc = useQueryClient();
  const [text, setText] = useState("");
  const scroller = useRef<HTMLDivElement>(null);

  const { data: detail } = useQuery({
    queryKey: ["inbox-detail", cid],
    queryFn: () => getInboxDetail(cid),
    refetchInterval: 4000, // catch end-user messages while handed off
  });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["inbox-detail", cid] });
    onChanged();
  };
  const doTakeover = useMutation({ mutationFn: () => takeover(cid), onSuccess: invalidate });
  const doHandback = useMutation({ mutationFn: () => handback(cid), onSuccess: invalidate });
  const doClose = useMutation({ mutationFn: () => closeConversation(cid), onSuccess: invalidate });
  const doReply = useMutation({
    mutationFn: (t: string) => replyInbox(cid, t),
    onSuccess: () => {
      setText("");
      invalidate();
    },
  });

  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight });
  }, [detail?.messages.length]);

  const handoff = detail?.handoff;
  const isHandoff = detail?.status === "handoff";
  const assigned = Boolean(handoff?.assigned_to);

  return (
    <div className="flex flex-col">
      <div className="flex items-center gap-2 border-b border-border p-3">
        <UserCog className="size-4 text-ember-soft" />
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-medium text-text">{detail?.title || "Conversation"}</div>
          <div className="text-xs capitalize text-faint">
            {detail?.channel} · {detail?.status}
            {handoff?.reason ? ` · reason: ${handoff.reason}` : ""}
          </div>
        </div>
        {isHandoff && !assigned && (
          <Button size="sm" variant="primary" onClick={() => doTakeover.mutate()} disabled={doTakeover.isPending}>
            <Headphones className="size-4" /> Take over
          </Button>
        )}
        {isHandoff && assigned && (
          <Button size="sm" variant="outline" onClick={() => doHandback.mutate()} disabled={doHandback.isPending}>
            <Bot className="size-4" /> Hand back
          </Button>
        )}
        {detail?.status !== "closed" && (
          <Button size="sm" variant="outline" onClick={() => doClose.mutate()} disabled={doClose.isPending}>
            <Check className="size-4" /> Close
          </Button>
        )}
      </div>

      <div ref={scroller} className="flex-1 space-y-3 overflow-y-auto scroll-thin p-4">
        {(detail?.messages ?? []).map((m) => {
          const who = m.role === "user" ? "user" : "assistant";
          const operator = m.provider === "operator";
          return (
            <div key={m.id} className={`flex gap-2 ${who === "user" ? "flex-row-reverse" : ""}`}>
              <span className="grid size-7 shrink-0 place-items-center rounded-md border border-border bg-surface-2 text-faint">
                {who === "user" ? (
                  <User className="size-3.5" />
                ) : operator ? (
                  <Headphones className="size-3.5 text-ember-soft" />
                ) : (
                  <Bot className="size-3.5 text-ember-soft" />
                )}
              </span>
              <div
                className={`max-w-[80%] whitespace-pre-wrap rounded-lg border px-3 py-2 text-sm ${
                  who === "user"
                    ? "border-ember/30 bg-ember/[0.06] text-text"
                    : operator
                      ? "border-ember/40 bg-ember/[0.1] text-text"
                      : "border-border bg-surface-2/60 text-text"
                }`}
              >
                {operator && (
                  <div className="mb-0.5 text-[10px] uppercase tracking-wide text-ember-soft">Operator</div>
                )}
                {m.content}
              </div>
            </div>
          );
        })}
      </div>

      {isHandoff && assigned ? (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (text.trim()) doReply.mutate(text.trim());
          }}
          className="flex items-center gap-2 border-t border-border p-3"
        >
          <input
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Reply as an operator…"
            className="h-10 flex-1 rounded-md border border-border bg-surface-2 px-3 text-sm text-text placeholder:text-faint focus-visible:border-ember/60 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ember/40"
          />
          <Button type="submit" variant="primary" disabled={!text.trim() || doReply.isPending} aria-label="Send reply">
            {doReply.isPending ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />}
          </Button>
        </form>
      ) : (
        <div className="border-t border-border p-3 text-center text-xs text-muted">
          {isHandoff ? "Take over to reply." : "The assistant is handling this conversation."}
        </div>
      )}
    </div>
  );
}
