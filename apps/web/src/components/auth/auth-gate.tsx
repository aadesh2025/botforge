"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import { me } from "@/lib/api/auth";
import { createOrg, listOrgs } from "@/lib/api/orgs";
import { getAccessToken, getActiveOrgId, setActiveOrgId, clearAuth } from "@/lib/api/tokens";
import { useSession } from "@/lib/store/session";
import { LogoMark } from "@/components/brand/logo";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

/** Bootstraps the session on the client: loads /me + orgs, or bounces to /login. */
export function AuthGate({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { ready, orgs, setSession } = useSession();

  useEffect(() => {
    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const [profile, loaded] = await Promise.all([me(), listOrgs()]);
        if (cancelled) return;
        const stored = getActiveOrgId();
        const active = loaded.find((o) => o.id === stored)?.id ?? loaded[0]?.id ?? null;
        if (active) setActiveOrgId(active);
        setSession(profile.user, loaded, active);
      } catch {
        if (cancelled) return;
        clearAuth();
        router.replace("/login");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [router, setSession]);

  if (!ready) {
    return <Splash label="Loading your workspace…" />;
  }
  if (orgs.length === 0) {
    return <CreateFirstOrg />;
  }
  return <>{children}</>;
}

function Splash({ label }: { label: string }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-bg">
      <div className="flex items-center gap-2 text-muted">
        <LogoMark className="animate-pulse" />
        <span className="text-sm">{label}</span>
      </div>
    </div>
  );
}

function CreateFirstOrg() {
  const { setSession, user } = useSession();
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);

  async function onCreate(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const org = await createOrg(name);
      setActiveOrgId(org.id);
      if (user) setSession(user, [org], org.id);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="relative flex min-h-screen items-center justify-center bg-bg px-4">
      <div className="glow-ember pointer-events-none absolute inset-0" />
      <div className="relative w-full max-w-sm rounded-xl border border-border bg-surface p-6 shadow-pop">
        <h1 className="font-display text-xl font-semibold text-text">Create your organization</h1>
        <p className="mt-1 text-sm text-muted">Everything in BotForge lives inside an organization.</p>
        <form onSubmit={onCreate} className="mt-6 space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="org">Organization name</Label>
            <Input id="org" required autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="Acme Inc." />
          </div>
          <Button type="submit" variant="primary" size="lg" className="w-full" disabled={busy || !name.trim()}>
            {busy && <Loader2 className="size-4 animate-spin" />} Create organization
          </Button>
        </form>
      </div>
    </div>
  );
}
