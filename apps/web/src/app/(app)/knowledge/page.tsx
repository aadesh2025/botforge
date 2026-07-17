import Link from "next/link";
import { BookOpen, Database, Plus } from "lucide-react";
import { PageHeader } from "@/components/dashboard/page-header";
import { Button } from "@/components/ui/button";
import { knowledgeBases } from "@/lib/mock/builder";
import { compact, relativeTime } from "@/lib/utils";

export default function KnowledgePage() {
  return (
    <div className="mx-auto max-w-[1400px] space-y-6">
      <PageHeader title="Knowledge" description="Documents your agents retrieve answers from.">
        <Button variant="primary">
          <Plus /> New knowledge base
        </Button>
      </PageHeader>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {knowledgeBases.map((kb) => (
          <Link
            key={kb.id}
            href={`/knowledge/${kb.id}`}
            className="group relative overflow-hidden rounded-lg border border-border bg-surface p-5 transition-colors hover:border-border-strong"
          >
            <span className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-ember/70 to-transparent opacity-0 transition-opacity group-hover:opacity-100" />
            <div className="flex items-start justify-between">
              <span className="grid size-11 place-items-center rounded-lg border border-border bg-surface-2 text-ember-soft">
                <BookOpen className="size-5" />
              </span>
              <span className="text-xs text-faint">{relativeTime(kb.updatedAt)}</span>
            </div>
            <h3 className="mt-4 font-display text-lg font-semibold text-text">{kb.name}</h3>
            <div className="mt-4 flex items-center gap-5 border-t border-border pt-4 text-sm">
              <div>
                <div className="font-semibold text-text">{kb.docs}</div>
                <div className="text-[11px] text-faint">documents</div>
              </div>
              <div>
                <div className="font-semibold text-text">{compact(kb.chunks)}</div>
                <div className="text-[11px] text-faint">chunks</div>
              </div>
            </div>
          </Link>
        ))}

        <button className="flex min-h-[180px] flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-border-strong bg-surface/40 text-muted transition-colors hover:border-ember/40 hover:bg-ember/[0.03] hover:text-ember-soft">
          <span className="grid size-11 place-items-center rounded-lg border border-border bg-surface-2">
            <Database className="size-5" />
          </span>
          <span className="text-sm font-medium">Create a knowledge base</span>
        </button>
      </div>
    </div>
  );
}
