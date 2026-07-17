import { KeyRound, Plus, Trash2 } from "lucide-react";
import { Section } from "@/components/settings/section";
import { Button } from "@/components/ui/button";
import { apiKeys } from "@/lib/mock/settings";
import { relativeTime } from "@/lib/utils";

export default function ApiKeysPage() {
  return (
    <Section
      title="API keys"
      description="Programmatic access to the BotForge API, scoped to this org."
      action={
        <Button variant="primary" size="sm">
          <Plus /> Create key
        </Button>
      }
      noPad
    >
      <ul className="divide-y divide-border">
        {apiKeys.map((k) => (
          <li key={k.id} className="flex items-center gap-3 px-5 py-3.5">
            <span className="grid size-9 place-items-center rounded-md border border-border bg-surface-2 text-ember-soft">
              <KeyRound className="size-4" />
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-text">{k.name}</span>
                <code className="rounded bg-surface-2 px-1.5 py-0.5 font-mono text-[11px] text-muted">
                  {k.prefix}••••
                </code>
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-1.5">
                {k.scopes.map((s) => (
                  <span key={s} className="rounded border border-border bg-surface-2 px-1.5 py-0.5 font-mono text-[10px] text-faint">
                    {s}
                  </span>
                ))}
              </div>
            </div>
            <div className="hidden text-right sm:block">
              <div className="text-xs text-muted">
                {k.lastUsed ? `Used ${relativeTime(k.lastUsed)}` : "Never used"}
              </div>
              <div className="text-[11px] text-faint">Created {relativeTime(k.createdAt)}</div>
            </div>
            <button className="rounded-md p-1.5 text-faint transition-colors hover:bg-surface-2 hover:text-error" aria-label="Revoke key">
              <Trash2 className="size-4" />
            </button>
          </li>
        ))}
      </ul>
    </Section>
  );
}
