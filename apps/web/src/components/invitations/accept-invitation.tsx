"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { AlertTriangle, Loader2, MailX, UserX } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { acceptInvitation, listOrgs } from "@/lib/api/orgs";
import { login, me, signup } from "@/lib/api/auth";
import { ApiError } from "@/lib/api/client";
import { getAccessToken, setActiveOrgId } from "@/lib/api/tokens";
import { useSession } from "@/lib/store/session";

/** The three failures the server actually models, each worth its own explanation. */
const FAILURES: Record<string, { icon: typeof MailX; title: string; detail: string }> = {
  "org.invitation_invalid": {
    icon: MailX,
    title: "This invitation has expired",
    detail:
      "Invitations are valid for 7 days, and each one can only be used once. Ask whoever invited you to send a new one.",
  },
  "org.invite_email_mismatch": {
    icon: UserX,
    title: "This invitation is for a different email",
    detail:
      "You're signed in with an account the invitation wasn't sent to. Sign out and use the address the email was sent to.",
  },
  "org.not_found": {
    icon: AlertTriangle,
    title: "That organization no longer exists",
    detail: "It looks like it was deleted after the invitation was sent.",
  },
};

type Mode = "login" | "signup";

export function AcceptInvitation() {
  const router = useRouter();
  const params = useSearchParams();
  const token = params.get("token") ?? "";
  const setSession = useSession((s) => s.setSession);

  // Derived at first render rather than set from an effect: whether we can redeem straight
  // away is knowable immediately from the token and the stored session.
  const [status, setStatus] = useState<"working" | "needs-account" | "failed">(() => {
    if (typeof window === "undefined") return "working"; // no cookies to read during SSR
    if (!params.get("token")) return "failed";
    return getAccessToken() ? "working" : "needs-account";
  });
  const [errorCode, setErrorCode] = useState<string | null>(() =>
    typeof window !== "undefined" && !params.get("token") ? "org.invitation_invalid" : null,
  );
  const [formError, setFormError] = useState<string | null>(null);
  const [mode, setMode] = useState<Mode>("signup");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [busy, setBusy] = useState(false);
  // A React 18 double-mount in dev would otherwise burn the single-use token.
  const attempted = useRef(false);

  /** Redeem the token with whatever session is current, then land in the new org. */
  async function accept(): Promise<boolean> {
    try {
      const org = await acceptInvitation(token);
      // Make the org they just joined the active one, so /dashboard opens on it.
      setActiveOrgId(org.id);
      const [profile, orgs] = await Promise.all([me(), listOrgs()]);
      setSession(profile.user, orgs.length ? orgs : [org], org.id);
      router.replace("/dashboard");
      return true;
    } catch (e) {
      const code = e instanceof ApiError ? e.code : null;
      setErrorCode(code);
      setStatus("failed");
      return false;
    }
  }

  // Redeem on load when there's already a session. The ref guards against React's
  // double-mount in dev burning the single-use token.
  useEffect(() => {
    if (attempted.current || status !== "working" || !token) return;
    attempted.current = true;
    void accept();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, status]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setFormError(null);
    try {
      if (mode === "signup") {
        await signup(email.trim(), password, fullName.trim() || undefined);
      } else {
        await login(email.trim(), password);
      }
      // Straight on to accepting — don't drop them on the dashboard having silently
      // failed to join the org they were invited to.
      await accept();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Something went wrong. Try again.");
    } finally {
      setBusy(false);
    }
  }

  if (status === "working") {
    return (
      <div className="flex items-center gap-3 text-sm text-muted">
        <Loader2 className="size-4 animate-spin text-ember-soft" />
        Joining…
      </div>
    );
  }

  if (status === "failed") {
    const failure = FAILURES[errorCode ?? ""] ?? {
      icon: AlertTriangle,
      title: "We couldn't accept this invitation",
      detail: "Please ask whoever invited you to send a new one.",
    };
    const Icon = failure.icon;
    return (
      <div className="rounded-lg border border-border bg-surface p-6">
        <Icon className="mb-3 size-6 text-warn" aria-hidden />
        <h1 className="font-display text-lg font-semibold text-text">{failure.title}</h1>
        <p className="mt-2 text-sm text-muted">{failure.detail}</p>
        <Button variant="outline" className="mt-4" onClick={() => router.push("/login")}>
          Go to sign in
        </Button>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-border bg-surface p-6">
      <h1 className="font-display text-lg font-semibold text-text">You&rsquo;ve been invited</h1>
      <p className="mt-1 text-sm text-muted">
        {mode === "signup"
          ? "Create your account with the email the invitation was sent to."
          : "Sign in with the email the invitation was sent to."}
      </p>

      <form onSubmit={onSubmit} className="mt-5 space-y-3">
        {mode === "signup" && (
          <div>
            <label htmlFor="invite-name" className="mb-1 block text-xs text-muted">
              Your name
            </label>
            <Input
              id="invite-name"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="Aadesh Kumar"
            />
          </div>
        )}
        <div>
          <label htmlFor="invite-email" className="mb-1 block text-xs text-muted">
            Email
          </label>
          <Input
            id="invite-email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@company.com"
          />
        </div>
        <div>
          <label htmlFor="invite-password" className="mb-1 block text-xs text-muted">
            Password
          </label>
          <Input
            id="invite-password"
            type="password"
            autoComplete={mode === "signup" ? "new-password" : "current-password"}
            required
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>

        {formError && <p className="text-sm text-error">{formError}</p>}

        <Button type="submit" variant="primary" className="w-full" disabled={busy}>
          {busy && <Loader2 className="size-4 animate-spin" />}
          {mode === "signup" ? "Create account & join" : "Sign in & join"}
        </Button>
      </form>

      <button
        type="button"
        onClick={() => {
          setMode(mode === "signup" ? "login" : "signup");
          setFormError(null);
        }}
        className="mt-4 text-xs text-muted underline hover:text-text"
      >
        {mode === "signup" ? "I already have an account" : "I need to create an account"}
      </button>
    </div>
  );
}
