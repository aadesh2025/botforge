"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, Bot, Building2, CircleDollarSign, Database, MessagesSquare, Server, Users, Zap } from "lucide-react";
import { PageHeader } from "@/components/dashboard/page-header";
import { StatCard } from "@/components/dashboard/stat-card";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import {
  getAdminHealth,
  getPlatformUsage,
  listAdminOrgs,
  listAdminUsers,
  listFeatureFlags,
  upsertFeatureFlag,
  type FeatureFlag,
} from "@/lib/api/admin";
import { useSession } from "@/lib/store/session";
import { compact, usd } from "@/lib/utils";

export default function AdminPage() {
  const router = useRouter();
  const { user, ready } = useSession();
  const staff = Boolean(user?.is_staff);

  // Route guard: real enforcement is the API's 403, but non-staff shouldn't see the console.
  useEffect(() => {
    if (ready && !staff) router.replace("/dashboard");
  }, [ready, staff, router]);

  const { data: usage } = useQuery({ queryKey: ["admin-usage"], queryFn: getPlatformUsage, enabled: staff });
  const { data: health } = useQuery({ queryKey: ["admin-health"], queryFn: getAdminHealth, enabled: staff, refetchInterval: 15_000 });
  const { data: orgs } = useQuery({ queryKey: ["admin-orgs"], queryFn: listAdminOrgs, enabled: staff });
  const { data: users } = useQuery({ queryKey: ["admin-users"], queryFn: listAdminUsers, enabled: staff });

  if (!ready || !staff) {
    return <div className="grid min-h-[40vh] place-items-center text-sm text-muted">Checking access…</div>;
  }

  return (
    <div className="mx-auto max-w-[1400px] space-y-6">
      <PageHeader title="Platform admin" description="Cross-tenant operations. Visible to platform staff only.">
        <Badge variant="ember">
          <Server className="size-3" /> staff
        </Badge>
      </PageHeader>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 xl:grid-cols-6">
        <StatCard label="Organizations" value={compact(usage?.organizations ?? 0)} icon={Building2} />
        <StatCard label="Users" value={compact(usage?.users ?? 0)} icon={Users} />
        <StatCard label="Agents" value={compact(usage?.agents ?? 0)} icon={Bot} />
        <StatCard label="Conversations" value={compact(usage?.conversations ?? 0)} icon={MessagesSquare} />
        <StatCard
          label="Tokens"
          value={compact((usage?.tokens_prompt ?? 0) + (usage?.tokens_completion ?? 0))}
          icon={Zap}
          hint="prompt + completion"
        />
        <StatCard label="Spend" value={usd((usage?.cost_micros ?? 0) / 1_000_000)} icon={CircleDollarSign} invertDelta />
      </div>

      <HealthPanel health={health} />

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <TopOrgs rows={usage?.top_orgs ?? []} />
        <FeatureFlags />
      </div>

      <OrgsTable orgs={orgs ?? []} />
      <UsersTable users={users ?? []} />
    </div>
  );
}

function HealthPanel({ health }: { health: { database: boolean; redis: boolean } | undefined }) {
  const Pill = ({ ok, label, icon: Icon }: { ok: boolean; label: string; icon: typeof Database }) => (
    <div className="flex items-center gap-2 rounded-md border border-border bg-surface-2 px-3 py-2">
      <Icon className="size-4 text-faint" />
      <span className="text-sm text-text">{label}</span>
      <Badge variant={ok ? "success" : "error"} className="ml-auto">
        {ok ? "healthy" : "down"}
      </Badge>
    </div>
  );
  return (
    <section className="rounded-lg border border-border bg-surface p-5">
      <div className="mb-4 flex items-center gap-2">
        <Activity className="size-4 text-ember-soft" />
        <h3 className="font-display text-base font-semibold text-text">System health</h3>
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Pill ok={Boolean(health?.database)} label="PostgreSQL" icon={Database} />
        <Pill ok={Boolean(health?.redis)} label="Redis" icon={Server} />
      </div>
    </section>
  );
}

function TopOrgs({ rows }: { rows: { organization_id: string; name: string; tokens_prompt: number; tokens_completion: number; cost_micros: number }[] }) {
  return (
    <section className="rounded-lg border border-border bg-surface">
      <div className="border-b border-border p-5">
        <h3 className="font-display text-base font-semibold text-text">Top orgs by tokens</h3>
        <p className="text-sm text-muted">Highest consumption across the platform.</p>
      </div>
      <ul className="divide-y divide-border">
        {rows.length === 0 && <li className="px-5 py-4 text-sm text-muted">No usage recorded yet.</li>}
        {rows.map((r, i) => (
          <li key={r.organization_id} className="flex items-center gap-3 px-5 py-3">
            <span className="font-mono text-xs text-faint">{String(i + 1).padStart(2, "0")}</span>
            <span className="flex-1 truncate text-sm text-text">{r.name}</span>
            <span className="font-mono text-sm text-muted">{compact(r.tokens_prompt + r.tokens_completion)} tok</span>
            <span className="font-mono text-xs text-faint">{usd(r.cost_micros / 1_000_000)}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function FeatureFlags() {
  const qc = useQueryClient();
  const { data: flags } = useQuery({ queryKey: ["admin-flags"], queryFn: listFeatureFlags });
  const toggle = useMutation({
    mutationFn: (f: FeatureFlag) => upsertFeatureFlag(f.key, !f.enabled, f.description),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-flags"] }),
  });

  return (
    <section className="rounded-lg border border-border bg-surface">
      <div className="border-b border-border p-5">
        <h3 className="font-display text-base font-semibold text-text">Feature flags</h3>
        <p className="text-sm text-muted">Platform-wide rollout switches.</p>
      </div>
      <ul className="divide-y divide-border">
        {(flags ?? []).length === 0 && <li className="px-5 py-4 text-sm text-muted">No flags defined.</li>}
        {(flags ?? []).map((f) => (
          <li key={f.key} className="flex items-center gap-3 px-5 py-3">
            <div className="min-w-0 flex-1">
              <div className="font-mono text-sm text-text">{f.key}</div>
              {f.description && <div className="truncate text-xs text-faint">{f.description}</div>}
            </div>
            <Switch checked={f.enabled} disabled={toggle.isPending} onCheckedChange={() => toggle.mutate(f)} />
          </li>
        ))}
      </ul>
    </section>
  );
}

function OrgsTable({ orgs }: { orgs: { id: string; name: string; slug: string | null; members: number; agents: number; deleted: boolean; created_at: string }[] }) {
  return (
    <section className="rounded-lg border border-border bg-surface">
      <div className="border-b border-border p-5">
        <h3 className="font-display text-base font-semibold text-text">Organizations</h3>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-xs uppercase tracking-wider text-faint">
              <th className="px-5 py-3 font-medium">Name</th>
              <th className="px-5 py-3 font-medium">Slug</th>
              <th className="px-5 py-3 text-right font-medium">Members</th>
              <th className="px-5 py-3 text-right font-medium">Agents</th>
              <th className="px-5 py-3 font-medium">Created</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {orgs.length === 0 && (
              <tr>
                <td colSpan={5} className="px-5 py-4 text-muted">No organizations.</td>
              </tr>
            )}
            {orgs.map((o) => (
              <tr key={o.id} className="hover:bg-surface-2/50">
                <td className="px-5 py-3 text-text">
                  <span className="flex items-center gap-2">
                    {o.name}
                    {o.deleted && <Badge variant="error">deleted</Badge>}
                  </span>
                </td>
                <td className="px-5 py-3 font-mono text-xs text-muted">{o.slug ?? "—"}</td>
                <td className="px-5 py-3 text-right font-mono text-muted">{o.members}</td>
                <td className="px-5 py-3 text-right font-mono text-muted">{o.agents}</td>
                <td className="px-5 py-3 text-faint">{new Date(o.created_at).toLocaleDateString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function UsersTable({ users }: { users: { id: string; email: string; is_staff: boolean; is_active: boolean; orgs: number; created_at: string }[] }) {
  return (
    <section className="rounded-lg border border-border bg-surface">
      <div className="border-b border-border p-5">
        <h3 className="font-display text-base font-semibold text-text">Users</h3>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-xs uppercase tracking-wider text-faint">
              <th className="px-5 py-3 font-medium">Email</th>
              <th className="px-5 py-3 font-medium">Status</th>
              <th className="px-5 py-3 text-right font-medium">Orgs</th>
              <th className="px-5 py-3 font-medium">Created</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {users.length === 0 && (
              <tr>
                <td colSpan={4} className="px-5 py-4 text-muted">No users.</td>
              </tr>
            )}
            {users.map((u) => (
              <tr key={u.id} className="hover:bg-surface-2/50">
                <td className="px-5 py-3 text-text">
                  <span className="flex items-center gap-2">
                    {u.email}
                    {u.is_staff && <Badge variant="ember">staff</Badge>}
                  </span>
                </td>
                <td className="px-5 py-3">
                  <Badge variant={u.is_active ? "success" : "outline"}>{u.is_active ? "active" : "disabled"}</Badge>
                </td>
                <td className="px-5 py-3 text-right font-mono text-muted">{u.orgs}</td>
                <td className="px-5 py-3 text-faint">{new Date(u.created_at).toLocaleDateString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
