import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, FileUp, Link2, Type, MoreHorizontal } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { DocIcon } from "@/components/shared/doc-icon";
import { knowledgeBases } from "@/lib/mock/builder";
import { kbDocuments, docStatusMeta } from "@/lib/mock/knowledge";
import { compact, relativeTime } from "@/lib/utils";

export default function KnowledgeDetailPage({ params }: { params: { id: string } }) {
  const kb = knowledgeBases.find((k) => k.id === params.id);
  if (!kb) notFound();
  const docs = kbDocuments[params.id] ?? [];

  return (
    <div className="mx-auto max-w-[1200px] space-y-6">
      <div className="flex items-center gap-3">
        <Link
          href="/knowledge"
          className="grid size-8 place-items-center rounded-md border border-border bg-surface text-muted transition-colors hover:text-text"
          aria-label="Back to knowledge"
        >
          <ArrowLeft className="size-4" />
        </Link>
        <div>
          <h1 className="font-display text-2xl font-semibold tracking-tight text-text">{kb.name}</h1>
          <p className="text-sm text-muted">
            {kb.docs} documents · {compact(kb.chunks)} chunks
          </p>
        </div>
      </div>

      {/* Add documents */}
      <div className="rounded-lg border border-border bg-surface p-5">
        <div className="grid gap-4 md:grid-cols-3">
          <div className="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-border-strong bg-surface-2/40 p-6 text-center transition-colors hover:border-ember/40 hover:bg-ember/[0.03]">
            <FileUp className="size-6 text-ember-soft" />
            <div className="text-sm font-medium text-text">Upload files</div>
            <div className="text-xs text-faint">PDF, DOCX, TXT, CSV, MD</div>
          </div>
          <div className="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-border-strong bg-surface-2/40 p-6 text-center transition-colors hover:border-ember/40 hover:bg-ember/[0.03]">
            <Link2 className="size-6 text-ember-soft" />
            <div className="text-sm font-medium text-text">Add a URL</div>
            <div className="text-xs text-faint">Crawl a web page</div>
          </div>
          <div className="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-border-strong bg-surface-2/40 p-6 text-center transition-colors hover:border-ember/40 hover:bg-ember/[0.03]">
            <Type className="size-6 text-ember-soft" />
            <div className="text-sm font-medium text-text">Paste text</div>
            <div className="text-xs text-faint">Raw content</div>
          </div>
        </div>
      </div>

      {/* Documents table */}
      <div className="overflow-hidden rounded-lg border border-border bg-surface">
        <div className="flex items-center justify-between border-b border-border p-5">
          <h3 className="font-display text-base font-semibold text-text">Documents</h3>
          <span className="text-sm text-muted">{docs.length} items</span>
        </div>
        <div className="overflow-x-auto scroll-thin">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-faint">
                <th className="px-5 py-3 font-medium">Name</th>
                <th className="px-5 py-3 font-medium">Status</th>
                <th className="px-5 py-3 font-medium">Chunks</th>
                <th className="px-5 py-3 font-medium">Added</th>
                <th className="px-5 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {docs.map((doc) => {
                const status = docStatusMeta[doc.status];
                return (
                  <tr key={doc.id} className="transition-colors hover:bg-surface-2/40">
                    <td className="px-5 py-3">
                      <div className="flex items-center gap-2.5">
                        <span className="grid size-8 place-items-center rounded-md border border-border bg-surface-2 text-faint">
                          <DocIcon type={doc.type} />
                        </span>
                        <span className="max-w-[280px] truncate font-medium text-text">{doc.name}</span>
                      </div>
                    </td>
                    <td className="px-5 py-3">
                      {doc.status === "processing" ? (
                        <div className="flex items-center gap-2">
                          <div className="h-1.5 w-20 overflow-hidden rounded-full bg-surface-3">
                            <div
                              className="h-full rounded-full bg-gradient-to-r from-ember to-ember-2"
                              style={{ width: `${doc.progress}%` }}
                            />
                          </div>
                          <span className="text-xs text-info">{doc.progress}%</span>
                        </div>
                      ) : (
                        <Badge variant={status.variant}>{status.label}</Badge>
                      )}
                    </td>
                    <td className="px-5 py-3 font-mono text-muted">{doc.chunks || "—"}</td>
                    <td className="px-5 py-3 text-faint">{relativeTime(doc.addedAt)}</td>
                    <td className="px-5 py-3 text-right">
                      <button className="rounded-md p-1.5 text-faint transition-colors hover:bg-surface-2 hover:text-text">
                        <MoreHorizontal className="size-4" />
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
