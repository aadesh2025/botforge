"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { AlertTriangle, Loader2, Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { replyInbox, sendTemplate, type ApiSendWindow } from "@/lib/api/inbox";

function closesAtLabel(iso: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

/**
 * The operator's composer.
 *
 * Splits on whether the platform will actually deliver a free-form message right now:
 * WhatsApp drops anything sent more than 24 hours after the customer last wrote, so the
 * text box is replaced by the only thing that *will* arrive — an approved template.
 * Letting someone type into a box whose contents silently vanish is the bug this fixes.
 */
export function ReplyBox({
  cid,
  sendWindow,
  onSent,
}: {
  cid: string;
  sendWindow: ApiSendWindow | null;
  onSent: () => void;
}) {
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);

  const doReply = useMutation({
    mutationFn: (t: string) => replyInbox(cid, t),
    onSuccess: () => {
      setText("");
      setError(null);
      onSent();
    },
    // The window can close between page load and send; say so instead of failing silently.
    onError: (e) => setError((e as Error).message),
  });

  const windowClosed = Boolean(sendWindow && !sendWindow.open);
  if (windowClosed) {
    return <TemplateComposer cid={cid} templates={sendWindow!.templates} closesAt={sendWindow!.closes_at} onSent={onSent} />;
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (text.trim()) doReply.mutate(text.trim());
      }}
      className="border-t border-border p-3"
    >
      <div className="flex items-center gap-2">
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Reply as an operator…"
          aria-label="Reply as an operator"
          className="h-10 flex-1 rounded-md border border-border bg-surface-2 px-3 text-sm text-text placeholder:text-faint focus-visible:border-ember/60 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ember/40"
        />
        <Button type="submit" variant="primary" disabled={!text.trim() || doReply.isPending} aria-label="Send reply">
          {doReply.isPending ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />}
        </Button>
      </div>
      {error && <p className="mt-2 text-xs text-error">{error}</p>}
    </form>
  );
}

/** Shown when free-form text can't be delivered — the template is the only way through. */
function TemplateComposer({
  cid,
  templates,
  closesAt,
  onSent,
}: {
  cid: string;
  templates: string[];
  closesAt: string | null;
  onSent: () => void;
}) {
  const [template, setTemplate] = useState(templates[0] ?? "");
  const [params, setParams] = useState("");
  const [error, setError] = useState<string | null>(null);

  const send = useMutation({
    mutationFn: () =>
      sendTemplate(
        cid,
        template,
        params
          .split(",")
          .map((p) => p.trim())
          .filter(Boolean),
      ),
    onSuccess: () => {
      setParams("");
      setError(null);
      onSent();
    },
    onError: (e) => setError((e as Error).message),
  });

  return (
    <div className="border-t border-border p-3">
      <div
        role="status"
        className="mb-3 flex items-start gap-2 rounded-md border border-warn/40 bg-warn/[0.08] p-2.5 text-xs text-text"
      >
        <AlertTriangle className="mt-px size-4 shrink-0 text-warn" aria-hidden />
        <div>
          <p className="font-medium">The 24-hour reply window has closed.</p>
          <p className="mt-0.5 text-muted">
            WhatsApp only delivers free-form messages within 24 hours of the customer’s last
            message{closesAt ? ` (closed ${closesAtLabel(closesAt)})` : ""}. Send an approved
            template to re-open the conversation.
          </p>
        </div>
      </div>

      {templates.length === 0 ? (
        <p className="text-xs text-muted">
          No approved templates on this channel yet. Register them in Meta Business Manager, then
          add their names to the channel’s config in the agent’s Channels tab.
        </p>
      ) : (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (template) send.mutate();
          }}
          className="flex flex-wrap items-center gap-2"
        >
          <label className="sr-only" htmlFor="wa-template">
            Approved template
          </label>
          <select
            id="wa-template"
            value={template}
            onChange={(e) => setTemplate(e.target.value)}
            className="h-10 rounded-md border border-border bg-surface-2 px-2 text-sm text-text"
          >
            {templates.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
          <input
            value={params}
            onChange={(e) => setParams(e.target.value)}
            placeholder="Template values, comma-separated"
            aria-label="Template values, comma-separated"
            className="h-10 min-w-0 flex-1 rounded-md border border-border bg-surface-2 px-3 text-sm text-text placeholder:text-faint focus-visible:border-ember/60 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ember/40"
          />
          <Button type="submit" variant="primary" disabled={!template || send.isPending}>
            {send.isPending ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />}
            Send template
          </Button>
        </form>
      )}
      {error && <p className="mt-2 text-xs text-error">{error}</p>}
    </div>
  );
}
