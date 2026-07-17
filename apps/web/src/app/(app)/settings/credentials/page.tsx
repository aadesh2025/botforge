import { Plus, PlugZap } from "lucide-react";
import { Section } from "@/components/settings/section";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { credentials } from "@/lib/mock/settings";
import { providerLabel } from "@/lib/display";

const statusMeta = {
  valid: { label: "Valid", variant: "success" as const },
  untested: { label: "Untested", variant: "default" as const },
  invalid: { label: "Invalid", variant: "error" as const },
};

export default function CredentialsPage() {
  return (
    <Section
      title="Provider keys"
      description="Bring your own LLM keys. Encrypted at rest, never logged."
      action={
        <Button variant="outline" size="sm">
          <Plus /> Add key
        </Button>
      }
      noPad
    >
      <ul className="divide-y divide-border">
        {credentials.map((c) => {
          const status = statusMeta[c.status];
          return (
            <li key={c.id} className="flex items-center gap-3 px-5 py-3.5">
              <span className="grid size-9 place-items-center rounded-md border border-border bg-surface-2 text-ember-soft">
                <PlugZap className="size-4" />
              </span>
              <div className="min-w-0 flex-1">
                <div className="text-sm font-medium text-text">{c.label}</div>
                <div className="flex items-center gap-2 text-xs text-faint">
                  <span>{providerLabel[c.provider]}</span>
                  <span className="text-border-strong">·</span>
                  <span className="font-mono">{c.masked}</span>
                </div>
              </div>
              <Badge variant={status.variant}>{status.label}</Badge>
              <Button variant="ghost" size="sm">
                Test
              </Button>
            </li>
          );
        })}
      </ul>
    </Section>
  );
}
