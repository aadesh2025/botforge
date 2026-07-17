import { Calendar, CircleDollarSign, Download, MessagesSquare, ShieldCheck, Timer } from "lucide-react";
import { PageHeader } from "@/components/dashboard/page-header";
import { StatCard } from "@/components/dashboard/stat-card";
import { UsageChart } from "@/components/dashboard/usage-chart";
import { BarList } from "@/components/analytics/bar-list";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { usageSeries, dashboardSummary as s } from "@/lib/mock/data";
import { channelBreakdown, latencyBuckets, topQuestions, unansweredQuestions } from "@/lib/mock/analytics";
import { compact, usd } from "@/lib/utils";

export default function AnalyticsPage() {
  return (
    <div className="mx-auto max-w-[1400px] space-y-6">
      <PageHeader title="Analytics" description="How your agents are performing across channels.">
        <Button variant="outline" size="default">
          <Calendar /> Last 14 days
        </Button>
        <Button variant="outline" size="default">
          <Download /> Export CSV
        </Button>
      </PageHeader>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Conversations" value={compact(s.conversations7d)} delta={s.conversationsDelta} icon={MessagesSquare} hint="vs last period" />
        <StatCard label="Resolution rate" value={`${Math.round(s.resolutionRate * 100)}%`} delta={s.resolutionDelta} icon={ShieldCheck} hint="auto-resolved" />
        <StatCard label="Avg first token" value="0.9s" delta={-6.5} icon={Timer} hint="p50 latency" invertDelta />
        <StatCard label="Est. cost" value={usd(s.cost7d)} delta={s.costDelta} icon={CircleDollarSign} hint="this period" invertDelta />
      </div>

      <UsageChart data={usageSeries} />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <section className="rounded-lg border border-border bg-surface">
          <div className="border-b border-border p-5">
            <h3 className="font-display text-base font-semibold text-text">Conversations by channel</h3>
          </div>
          <div className="p-5">
            <BarList
              items={channelBreakdown.map((c) => ({ label: c.channel, value: Math.round(c.share * 1000) }))}
              format={(n) => `${(n / 10).toFixed(0)}%`}
            />
          </div>
        </section>

        <section className="rounded-lg border border-border bg-surface">
          <div className="border-b border-border p-5">
            <h3 className="font-display text-base font-semibold text-text">First-token latency</h3>
          </div>
          <div className="p-5">
            <BarList items={latencyBuckets.map((b) => ({ label: b.label, value: b.count }))} />
          </div>
        </section>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <section className="rounded-lg border border-border bg-surface">
          <div className="border-b border-border p-5">
            <h3 className="font-display text-base font-semibold text-text">Top questions</h3>
            <p className="text-sm text-muted">Most asked, answered from knowledge.</p>
          </div>
          <ul className="divide-y divide-border">
            {topQuestions.map((q, i) => (
              <li key={q.q} className="flex items-center gap-3 px-5 py-3">
                <span className="font-mono text-xs text-faint">{String(i + 1).padStart(2, "0")}</span>
                <span className="flex-1 truncate text-sm text-text">{q.q}</span>
                <span className="font-mono text-sm text-muted">{q.count}</span>
              </li>
            ))}
          </ul>
        </section>

        <section className="rounded-lg border border-border bg-surface">
          <div className="border-b border-border p-5">
            <h3 className="font-display text-base font-semibold text-text">Unanswered questions</h3>
            <p className="text-sm text-muted">Gaps to fill in your knowledge base.</p>
          </div>
          <ul className="divide-y divide-border">
            {unansweredQuestions.map((q) => (
              <li key={q.q} className="flex items-center gap-3 px-5 py-3">
                <Badge variant="warn">gap</Badge>
                <span className="flex-1 truncate text-sm text-text">{q.q}</span>
                <span className="font-mono text-sm text-muted">{q.count}</span>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  );
}
