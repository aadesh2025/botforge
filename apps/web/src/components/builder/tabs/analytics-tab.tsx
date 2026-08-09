"use client";

import { useQuery } from "@tanstack/react-query";
import { CircleDollarSign, MessagesSquare, ShieldCheck, Timer, Users, Zap } from "lucide-react";
import { StatCard } from "@/components/dashboard/stat-card";
import { UsageChart } from "@/components/dashboard/usage-chart";
import { ChannelBreakdown } from "@/components/analytics/channel-breakdown";
import {
  getLatency,
  getOverview,
  getSeries,
  getTopQuestions,
  getUnanswered,
} from "@/lib/api/analytics";
import { useSession } from "@/lib/store/session";
import { compact, usd } from "@/lib/utils";

/**
 * One agent's own analytics.
 *
 * Every query is the org-wide endpoint narrowed by `agent_id`, so this view and the
 * dashboard can never disagree — there is one aggregation in the backend and two filters
 * over it. Traffic from the Playground shows up here too (as the `playground` channel),
 * which is usually the first thing a freshly-built agent has.
 */
export function AnalyticsTab({ agentId }: { agentId: string | null }) {
  const activeOrgId = useSession((s) => s.activeOrgId);
  const enabled = Boolean(activeOrgId && agentId);
  const params = { agent_id: agentId ?? undefined };

  const { data: overview, isLoading: overviewLoading } = useQuery({
    queryKey: ["agent-overview", agentId, activeOrgId],
    queryFn: () => getOverview(params),
    enabled,
  });
  const { data: series, isLoading: seriesLoading } = useQuery({
    queryKey: ["agent-series", agentId, activeOrgId],
    queryFn: () => getSeries(params),
    enabled,
  });
  const { data: latency } = useQuery({
    queryKey: ["agent-latency", agentId, activeOrgId],
    queryFn: () => getLatency(params),
    enabled,
  });
  const { data: top } = useQuery({
    queryKey: ["agent-top", agentId, activeOrgId],
    queryFn: () => getTopQuestions(params),
    enabled,
  });
  const { data: unanswered } = useQuery({
    queryKey: ["agent-unanswered", agentId, activeOrgId],
    queryFn: () => getUnanswered(params),
    enabled,
  });

  if (!agentId) return null;

  const tokens = (overview?.tokens_prompt ?? 0) + (overview?.tokens_completion ?? 0);
  const cost = (overview?.cost_micros ?? 0) / 1_000_000;
  const costHint = tokens > 0 && cost === 0 ? "free tier — no billable usage" : "last 30d";

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Conversations"
          value={compact(overview?.conversations ?? 0)}
          icon={MessagesSquare}
          hint="last 30d"
        />
        <StatCard
          label="Resolution rate"
          value={overview?.conversations ? `${Math.round((overview.resolution_rate ?? 0) * 100)}%` : "—"}
          icon={ShieldCheck}
          hint="no human needed"
        />
        <StatCard label="Tokens used" value={compact(tokens)} icon={Zap} hint="prompt + completion" />
        <StatCard label="Est. cost" value={usd(cost)} icon={CircleDollarSign} hint={costHint} invertDelta />
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatCard
          label="Messages"
          value={compact(overview?.messages ?? 0)}
          icon={MessagesSquare}
          hint="user + assistant"
        />
        <StatCard label="Unique users" value={compact(overview?.users ?? 0)} icon={Users} hint="across channels" />
        <StatCard
          label="p50 latency"
          value={latency?.count ? `${latency.p50_ms} ms` : "—"}
          icon={Timer}
          hint="assistant replies"
          invertDelta
        />
      </div>

      <UsageChart data={series} isLoading={seriesLoading} title="This agent's activity" />

      <section
        aria-labelledby="agent-by-channel"
        className="overflow-hidden rounded-lg border border-border bg-surface"
      >
        <div className="border-b border-border p-5">
          <h3 id="agent-by-channel" className="font-display text-base font-semibold text-text">
            By channel
          </h3>
          <p className="text-sm text-muted">
            Where this agent’s conversations came from. Playground is your own testing.
          </p>
        </div>
        <div className="overflow-x-auto">
          <ChannelBreakdown buckets={overview?.by_channel} isLoading={overviewLoading} />
        </div>
      </section>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <section className="rounded-lg border border-border bg-surface">
          <div className="border-b border-border p-5">
            <h3 className="font-display text-base font-semibold text-text">Top questions</h3>
            <p className="text-sm text-muted">What people actually ask this agent.</p>
          </div>
          <ul className="divide-y divide-border">
            {(top ?? []).length === 0 && <li className="px-5 py-4 text-sm text-muted">No data yet.</li>}
            {(top ?? []).map((q, i) => (
              <li key={i} className="flex items-center gap-3 px-5 py-3">
                <span className="font-mono text-xs text-faint">{String(i + 1).padStart(2, "0")}</span>
                <span className="flex-1 truncate text-sm text-text">{q.question}</span>
                <span className="font-mono text-sm text-muted">{q.count}</span>
              </li>
            ))}
          </ul>
        </section>

        <section className="rounded-lg border border-border bg-surface">
          <div className="border-b border-border p-5">
            <h3 className="font-display text-base font-semibold text-text">Escalated questions</h3>
            <p className="text-sm text-muted">Where it needed a human — gaps to fill in its knowledge.</p>
          </div>
          <ul className="divide-y divide-border">
            {(unanswered ?? []).length === 0 && (
              <li className="px-5 py-4 text-sm text-muted">None — nice.</li>
            )}
            {(unanswered ?? []).map((q, i) => (
              <li key={i} className="flex items-center gap-3 px-5 py-3">
                <span className="flex-1 truncate text-sm text-text">{q.question}</span>
                <span className="font-mono text-sm text-muted">{q.count}</span>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  );
}
