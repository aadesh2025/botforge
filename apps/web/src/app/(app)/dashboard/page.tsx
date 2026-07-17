import { CircleDollarSign, MessagesSquare, Plus, ShieldCheck, Zap } from "lucide-react";
import { PageHeader } from "@/components/dashboard/page-header";
import { StatCard } from "@/components/dashboard/stat-card";
import { UsageChart } from "@/components/dashboard/usage-chart";
import { AgentsPanel } from "@/components/dashboard/agents-panel";
import { ConversationsPanel } from "@/components/dashboard/conversations-panel";
import { Button } from "@/components/ui/button";
import { agents, dashboardSummary as s, recentConversations, usageSeries } from "@/lib/mock/data";
import { compact, usd } from "@/lib/utils";

export default function DashboardPage() {
  return (
    <div className="mx-auto max-w-[1400px] space-y-6">
      {/* Header with a single restrained ember glow */}
      <div className="relative -mx-4 -mt-6 overflow-hidden px-4 pt-6 md:-mx-6 md:px-6 lg:-mx-8 lg:px-8">
        <div className="glow-ember pointer-events-none absolute inset-0 -z-10" />
        <PageHeader
          title="Dashboard"
          description="Everything your agents did in the last 7 days, at a glance."
        >
          <Button variant="outline" size="default">
            View reports
          </Button>
          <Button variant="primary" size="default">
            <Plus /> New agent
          </Button>
        </PageHeader>
      </div>

      {/* Stat row */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Conversations"
          value={compact(s.conversations7d)}
          delta={s.conversationsDelta}
          icon={MessagesSquare}
          hint="vs last 7d"
        />
        <StatCard
          label="Resolution rate"
          value={`${Math.round(s.resolutionRate * 100)}%`}
          delta={s.resolutionDelta}
          icon={ShieldCheck}
          hint="auto-resolved"
        />
        <StatCard
          label="Tokens used"
          value={compact(s.tokens7d)}
          delta={s.messagesDelta}
          icon={Zap}
          hint="across providers"
        />
        <StatCard
          label="Est. cost"
          value={usd(s.cost7d)}
          delta={s.costDelta}
          icon={CircleDollarSign}
          hint="this period"
          invertDelta
        />
      </div>

      {/* Two-column body */}
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <div className="space-y-6 xl:col-span-2">
          <UsageChart data={usageSeries} />
          <AgentsPanel agents={agents} />
        </div>
        <div className="xl:col-span-1">
          <ConversationsPanel conversations={recentConversations} />
        </div>
      </div>
    </div>
  );
}
