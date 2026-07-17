"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Loader2, Plus, PlugZap, Trash2, X } from "lucide-react";
import { Section } from "@/components/settings/section";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  createCredential,
  deleteCredential,
  listCredentials,
  listProviders,
  testCredential,
} from "@/lib/api/credentials";
import { useSession } from "@/lib/store/session";

export default function CredentialsPage() {
  const orgId = useSession((s) => s.activeOrgId);
  const qc = useQueryClient();
  const providers = useQuery({ queryKey: ["providers", orgId], queryFn: listProviders, enabled: Boolean(orgId) });
  const creds = useQuery({ queryKey: ["credentials", orgId], queryFn: listCredentials, enabled: Boolean(orgId) });

  const [open, setOpen] = useState(false);
  const [provider, setProvider] = useState("groq");
  const [apiKey, setApiKey] = useState("");
  const [label, setLabel] = useState("");
  const [busy, setBusy] = useState(false);
  const [testing, setTesting] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<Record<string, { ok: boolean; msg: string }>>({});

  async function onCreate(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await createCredential({ provider, api_key: apiKey, label: label || undefined, is_default: true });
      await qc.invalidateQueries({ queryKey: ["credentials", orgId] });
      setOpen(false);
      setApiKey("");
      setLabel("");
    } finally {
      setBusy(false);
    }
  }

  async function onTest(id: string) {
    setTesting(id);
    try {
      const r = await testCredential(id);
      setTestResult((s) => ({
        ...s,
        [id]: { ok: r.ok, msg: r.ok ? `${r.models?.length ?? 0} models` : r.error || "failed" },
      }));
    } finally {
      setTesting(null);
    }
  }

  async function onDelete(id: string) {
    await deleteCredential(id);
    await qc.invalidateQueries({ queryKey: ["credentials", orgId] });
  }

  return (
    <>
      <Section
        title="Provider keys"
        description="Bring your own LLM keys. Encrypted at rest, never shown in full."
        action={
          <Button variant="outline" size="sm" onClick={() => setOpen(true)}>
            <Plus /> Add key
          </Button>
        }
        noPad
      >
        {creds.isLoading ? (
          <div className="space-y-2 p-5">
            <Skeleton className="h-12" />
            <Skeleton className="h-12" />
          </div>
        ) : (creds.data ?? []).length === 0 ? (
          <div className="p-8 text-center text-sm text-muted">
            No provider keys yet. Add one to use a paid or keyed provider.
          </div>
        ) : (
          <ul className="divide-y divide-border">
            {(creds.data ?? []).map((c) => {
              const result = testResult[c.id];
              return (
                <li key={c.id} className="flex items-center gap-3 px-5 py-3.5">
                  <span className="grid size-9 place-items-center rounded-md border border-border bg-surface-2 text-ember-soft">
                    <PlugZap className="size-4" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-text">{c.label || c.provider}</span>
                      {c.is_default && <Badge variant="ember">default</Badge>}
                    </div>
                    <div className="flex items-center gap-2 text-xs text-faint">
                      <span>{c.provider}</span>
                      <span className="text-border-strong">·</span>
                      <span className="font-mono">{c.masked_key}</span>
                    </div>
                  </div>
                  {result && (
                    <Badge variant={result.ok ? "success" : "error"}>
                      {result.ok ? <Check className="size-3" /> : <X className="size-3" />}
                      {result.msg}
                    </Badge>
                  )}
                  <Button variant="ghost" size="sm" onClick={() => onTest(c.id)} disabled={testing === c.id}>
                    {testing === c.id ? <Loader2 className="size-3.5 animate-spin" /> : "Test"}
                  </Button>
                  <button
                    onClick={() => onDelete(c.id)}
                    className="rounded-md p-1.5 text-faint transition-colors hover:bg-surface-2 hover:text-error"
                    aria-label="Delete key"
                  >
                    <Trash2 className="size-4" />
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </Section>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add provider key</DialogTitle>
          </DialogHeader>
          <form onSubmit={onCreate} className="space-y-4">
            <Select value={provider} onValueChange={setProvider}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {(providers.data ?? []).map((p) => (
                  <SelectItem key={p.name} value={p.name}>
                    {p.label}
                    {p.free ? "  · free" : ""}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Input placeholder="Label (optional)" value={label} onChange={(e) => setLabel(e.target.value)} />
            <Input
              type="password"
              placeholder="API key"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              required
            />
            <Button type="submit" variant="primary" className="w-full" disabled={busy || !apiKey.trim()}>
              {busy && <Loader2 className="size-4 animate-spin" />} Save key
            </Button>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}
