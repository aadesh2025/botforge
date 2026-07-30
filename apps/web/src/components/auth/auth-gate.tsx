"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { ApiError } from "@/lib/api/client";
import { me } from "@/lib/api/auth";
import { listOrgs } from "@/lib/api/orgs";
import { getAccessToken, getActiveOrgId, setActiveOrgId, clearAuth } from "@/lib/api/tokens";
import { useSession } from "@/lib/store/session";
import { LogoMark } from "@/components/brand/logo";

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
      } catch (err) {
        if (cancelled) return;
        // Only a genuine auth failure may destroy the session. This bootstrap runs on every
        // page load, and navigating while it's still in flight **aborts** its requests — the
        // browser rejects them with a TypeError, not a 401. Treating that as "your token is
        // bad" logged people out for the crime of clicking a link too quickly, moments after
        // signing in. Anything that isn't a 401 (abort, offline, a 500) leaves the tokens
        // alone; the next load re-runs this and succeeds.
        if (err instanceof ApiError && err.status === 401) {
          clearAuth();
          router.replace("/login");
        }
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
    return <NoWorkspace />;
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

/** Shown to a signed-in account that belongs to no organization.
 *
 * Deliberately a dead end with no form. Workspaces are provisioned per client, so creating one
 * is staff-only server-side (`orgs.create_forbidden`) — offering a "Create organization" button
 * here would be offering a button that always 403s. The way in is an invitation, so the copy
 * names the email the invite has to be sent to, which is the one detail the recipient can act on.
 */
function NoWorkspace() {
  const user = useSession((s) => s.user);

  return (
    <div className="relative flex min-h-screen items-center justify-center bg-bg px-4">
      <div className="glow-ember pointer-events-none absolute inset-0" />
      <div className="relative w-full max-w-md rounded-xl border border-border bg-surface p-6 shadow-pop">
        <h1 className="font-display text-xl font-semibold text-text">No workspace yet</h1>
        <p className="mt-2 text-sm text-muted">
          Your account isn&apos;t linked to an organization. If you&apos;re expecting access, ask
          whoever invited you to send a fresh invite link to this email
          {user?.email ? (
            <>
              {" "}
              (<span className="font-mono text-text">{user.email}</span>)
            </>
          ) : null}{" "}
          — or contact your BotForge rep.
        </p>
        <p className="mt-4 text-xs text-faint">
          Already have an invite link? Open it while signed in and you&apos;ll join straight away.
        </p>
      </div>
    </div>
  );
}
