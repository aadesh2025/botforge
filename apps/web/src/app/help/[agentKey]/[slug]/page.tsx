import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { fetchPublicHelpArticle } from "@/lib/api/help-public";
import { renderMarkdown } from "@/lib/markdown";

export default async function HelpArticlePage({
  params,
}: {
  params: Promise<{ agentKey: string; slug: string }>;
}) {
  const { agentKey, slug } = await params;
  const article = await fetchPublicHelpArticle(agentKey, slug);
  // Unpublished and non-existent look the same from outside, by design.
  if (!article) notFound();

  return (
    <main className="mx-auto max-w-3xl px-6 py-16">
      <Link
        href={`/help/${agentKey}`}
        className="mb-8 inline-flex items-center gap-1.5 text-sm text-muted transition-colors hover:text-text"
      >
        <ArrowLeft className="size-4" /> All articles
      </Link>

      <article>
        <h1 className="font-display text-3xl font-semibold tracking-tight text-text">{article.title}</h1>
        {article.category && <p className="mt-2 text-sm text-faint">{article.category}</p>}
        <div
          className="help-article mt-8 space-y-4 text-text"
          // Authored by the org's own staff and escaped in renderMarkdown before any
          // formatting is applied, so no visitor-supplied HTML can reach this.
          dangerouslySetInnerHTML={{ __html: renderMarkdown(article.body_markdown) }}
        />
      </article>
    </main>
  );
}
