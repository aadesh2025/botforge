"use client";

import { useQuery } from "@tanstack/react-query";
import { CircleDollarSign, MessagesSquare, ShieldCheck, Zap } from "lucide-react";
import { StatCard } from "@/components/dashboard/stat-card";
import { UsageChart } from "@/components/dashboard/usage-chart";
import { ChannelBreakdown } from "@/components/analytics/channel-breakdown";
import { getOverview, getUsage } from "@/lib/api/analytics";
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
  const { data: usageDay } = useQuery({
    queryKey: ["dash-usage", activeOrgId],
    queryFn: () => getUsage({ group_by: "day" }),
    enabled,
  });

  const series = (usageDay ?? []).map((b) => ({
    date: b.key,
    tokens: b.tokens_prompt + b.tokens_completion,
    cost: b.cost_micros / 1_000_000,
    conversations: b.requests,
  }));
  const tokens = (overview?.tokens_prompt ?? 0) + (overview?.tokens_completion ?? 0);

  return (
    <>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Conversations" value={compact(overview?.conversations ?? 0)} icon={MessagesSquare} hint="last 30d" />
        <StatCard
          label="Resolution rate"
          value={`${Math.round((overview?.resolution_rate ?? 0) * 100)}%`}
          icon={ShieldCheck}
          hint="no human needed"
        />
        <StatCard label="Tokens used" value={compact(tokens)} icon={Zap} hint="across providers" />
        <StatCard
          label="Est. cost"
          value={usd((overview?.cost_micros ?? 0) / 1_000_000)}
          icon={CircleDollarSign}
          hint="last 30d"
          invertDelta
        />
      </div>
      {/* Side by side only when there's genuinely room; below xl the table would be
          squeezed to the point of clipping, so it stacks full width instead. */}
      <div className="grid grid-cols-1 gap-6 2xl:grid-cols-[1fr_420px]">
        <UsageChart data={series} />
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
    </>
  );
}
