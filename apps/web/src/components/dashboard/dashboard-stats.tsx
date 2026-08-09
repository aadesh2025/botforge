"use client";

import { useQuery } from "@tanstack/react-query";
import { CircleDollarSign, MessagesSquare, ShieldCheck, Zap } from "lucide-react";
import { StatCard } from "@/components/dashboard/stat-card";
import { UsageChart } from "@/components/dashboard/usage-chart";
import { AgentBreakdown } from "@/components/analytics/agent-breakdown";
import { ChannelBreakdown } from "@/components/analytics/channel-breakdown";
import { getByAgent, getOverview, getSeries } from "@/lib/api/analytics";
import { useSession } from "@/lib/store/session";
import { compact, usd } from "@/lib/utils";

export function DashboardStats() {
  const activeOrgId = useSession((s) => s.activeOrgId);
  const enabled = Boolean(activeOrgId);

  const { data: overview, isLoading: overviewLoading } = useQuery({
    queryKey: ["dash-overview", activeOrgId],
    queryFn: () => getOverview(),
    enabled,
  });
  // The chart's own source: gap-filled, one point per day, with real conversation counts.
  const { data: series, isLoading: seriesLoading } = useQuery({
    queryKey: ["dash-series", activeOrgId],
    queryFn: () => getSeries(),
    enabled,
  });
  const { data: byAgent, isLoading: byAgentLoading } = useQuery({
    queryKey: ["dash-by-agent", activeOrgId],
    queryFn: () => getByAgent(),
    enabled,
  });

  const tokens = (overview?.tokens_prompt ?? 0) + (overview?.tokens_completion ?? 0);
  const cost = (overview?.cost_micros ?? 0) / 1_000_000;
  // $0 across a month of real traffic is almost always the free tier, not a broken query —
  // say which, because a bare $0.00 next to 14k tokens reads as a bug.
  const costHint = tokens > 0 && cost === 0 ? "free tier — no billable usage" : "last 30d";

  return (
    <>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Conversations" value={compact(overview?.conversations ?? 0)} icon={MessagesSquare} hint="last 30d" />
        <StatCard
          label="Resolution rate"
          value={overview?.conversations ? `${Math.round((overview.resolution_rate ?? 0) * 100)}%` : "—"}
          icon={ShieldCheck}
          hint="no human needed"
        />
        <StatCard label="Tokens used" value={compact(tokens)} icon={Zap} hint="across providers" />
        <StatCard label="Est. cost" value={usd(cost)} icon={CircleDollarSign} hint={costHint} invertDelta />
      </div>

      {/* Side by side only when there's genuinely room; below xl the table would be
          squeezed to the point of clipping, so it stacks full width instead. */}
      <div className="grid grid-cols-1 gap-6 2xl:grid-cols-[1fr_420px]">
        <UsageChart data={series} isLoading={seriesLoading} />
        <section
          aria-labelledby="dash-by-channel"
          className="overflow-hidden rounded-lg border border-border bg-surface"
        >
          <div className="border-b border-border p-5">
            <h3 id="dash-by-channel" className="font-display text-base font-semibold text-text">
              By channel
            </h3>
            <p className="text-sm text-muted">Where your conversations came from.</p>
          </div>
          <div className="overflow-x-auto">
            <ChannelBreakdown buckets={overview?.by_channel} isLoading={overviewLoading} />
          </div>
        </section>
      </div>

      <section
        aria-labelledby="dash-by-agent"
        className="overflow-hidden rounded-lg border border-border bg-surface"
      >
        <div className="border-b border-border p-5">
          <h3 id="dash-by-agent" className="font-display text-base font-semibold text-text">
            By agent
          </h3>
          <p className="text-sm text-muted">
            How each agent is doing. Open one for its own analytics.
          </p>
        </div>
        <div className="overflow-x-auto">
          <AgentBreakdown buckets={byAgent} isLoading={byAgentLoading} />
        </div>
      </section>
    </>
  );
}
