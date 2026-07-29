import Link from "next/link";
import { fetchPublicHelpIndex } from "@/lib/api/help-public";

/** Public help index. Outside the authenticated (app) layout — visitors have no account. */
export default async function HelpIndexPage({ params }: { params: Promise<{ agentKey: string }> }) {
  const { agentKey } = await params;
  const articles = await fetchPublicHelpIndex(agentKey);

  // Grouped by category, with uncategorised last — a flat list stops being scannable fast.
  const groups = new Map<string, typeof articles>();
  for (const a of articles) {
    const key = a.category ?? "Other";
    groups.set(key, [...(groups.get(key) ?? []), a]);
  }

  return (
    <main className="mx-auto max-w-3xl px-6 py-16">
      <h1 className="font-display text-3xl font-semibold tracking-tight text-text">Help Center</h1>
      <p className="mt-2 text-muted">Answers to common questions.</p>

      {articles.length === 0 && (
        <p className="mt-10 rounded-lg border border-border bg-surface p-6 text-sm text-muted">
          No articles have been published yet.
        </p>
      )}

      <div className="mt-10 space-y-8">
        {[...groups.entries()].map(([category, items]) => (
          <section key={category}>
            <h2 className="mb-3 text-xs font-medium uppercase tracking-wide text-faint">{category}</h2>
            <ul className="divide-y divide-border overflow-hidden rounded-lg border border-border bg-surface">
              {items.map((a) => (
                <li key={a.slug}>
                  <Link
                    href={`/help/${agentKey}/${a.slug}`}
                    className="block px-4 py-3 text-sm text-text transition-colors hover:bg-surface-2/50"
                  >
                    {a.title}
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </main>
  );
}
