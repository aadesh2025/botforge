import { Plus } from "lucide-react";
import { PageHeader } from "@/components/dashboard/page-header";
import { DashboardStats } from "@/components/dashboard/dashboard-stats";
import { AgentsPanel } from "@/components/dashboard/agents-panel";
import { ConversationsPanel } from "@/components/dashboard/conversations-panel";
import { Button } from "@/components/ui/button";
import { agents, recentConversations } from "@/lib/mock/data";

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

      {/* Stat row + usage chart, wired to real analytics */}
      <DashboardStats />

      {/* Two-column body */}
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <div className="space-y-6 xl:col-span-2">
          <AgentsPanel agents={agents} />
        </div>
        <div className="xl:col-span-1">
          <ConversationsPanel conversations={recentConversations} />
        </div>
      </div>
    </div>
  );
}
