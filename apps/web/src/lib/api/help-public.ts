/** Public Help Center reads — no auth, no org header.
 *
 * Deliberately a separate module from `help-articles.ts`: that one is `"use client"` for
 * the authoring UI, and a client module's functions can't be called from a Server
 * Component. The public help pages render on the server.
 */

import { API_BASE } from "./config";

export interface PublicHelpArticleSummary {
  title: string;
  slug: string;
  category: string | null;
  updated_at: string;
}

export interface PublicHelpArticle extends PublicHelpArticleSummary {
  body_markdown: string;
}

export async function fetchPublicHelpIndex(agentKey: string): Promise<PublicHelpArticleSummary[]> {
  const res = await fetch(`${API_BASE}/v1/public/agents/${agentKey}/help`, { cache: "no-store" });
  if (!res.ok) return [];
  return res.json();
}

export async function fetchPublicHelpArticle(
  agentKey: string,
  slug: string,
): Promise<PublicHelpArticle | null> {
  const res = await fetch(`${API_BASE}/v1/public/agents/${agentKey}/help/${slug}`, {
    cache: "no-store",
  });
  if (!res.ok) return null;
  return res.json();
}
