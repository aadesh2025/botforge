import { Plus, Webhook } from "lucide-react";
import { Section } from "@/components/settings/section";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { webhooks } from "@/lib/mock/settings";
import { relativeTime } from "@/lib/utils";

const statusMeta = {
  active: { label: "Active", variant: "success" as const },
  failing: { label: "Failing", variant: "error" as const },
  disabled: { label: "Disabled", variant: "default" as const },
};

export default function WebhooksPage() {
  return (
    <Section
      title="Outbound webhooks"
      description="BotForge signs and delivers events to your endpoints, with retries."
      action={
        <Button variant="outline" size="sm">
          <Plus /> Add endpoint
        </Button>
      }
      noPad
    >
      <ul className="divide-y divide-border">
        {webhooks.map((w) => {
          const status = statusMeta[w.status];
          return (
            <li key={w.id} className="flex items-center gap-3 px-5 py-3.5">
              <span className="grid size-9 place-items-center rounded-md border border-border bg-surface-2 text-ember-soft">
                <Webhook className="size-4" />
              </span>
              <div className="min-w-0 flex-1">
                <div className="truncate font-mono text-sm text-text">{w.url}</div>
                <div className="mt-1 flex flex-wrap items-center gap-1.5">
                  {w.events.map((e) => (
                    <span key={e} className="rounded border border-border bg-surface-2 px-1.5 py-0.5 font-mono text-[10px] text-faint">
                      {e}
                    </span>
                  ))}
                </div>
              </div>
              <div className="hidden text-right sm:block">
                <div className="text-[11px] text-faint">
                  {w.lastDelivery ? `Delivered ${relativeTime(w.lastDelivery)}` : "No deliveries"}
                </div>
              </div>
              <Badge variant={status.variant}>{status.label}</Badge>
            </li>
          );
        })}
      </ul>
    </Section>
  );
}
