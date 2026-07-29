"use client";

import { api } from "./client";

export interface ApiHelpArticle {
  id: string;
  agent_id: string | null;
  title: string;
  slug: string;
  body_markdown: string;
  category: string | null;
  published: boolean;
  sync_to_kb: boolean;
  kb_document_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface PublicHelpArticleSummary {
  title: string;
  slug: string;
  category: string | null;
  updated_at: string;
}

export interface PublicHelpArticle extends PublicHelpArticleSummary {
  body_markdown: string;
}

/** Title → URL slug. Mirrors the server's rule so the preview matches what's saved. */
export function slugify(value: string): string {
  return (
    value
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 255) || "article"
  );
}

export function listHelpArticles(agentId?: string) {
  const qs = agentId ? `?agent_id=${agentId}` : "";
  return api<ApiHelpArticle[]>(`/v1/help-articles${qs}`, { orgScoped: true });
}

export function createHelpArticle(body: {
  agent_id: string;
  title: string;
  slug?: string;
  body_markdown: string;
  category?: string | null;
  published?: boolean;
  sync_to_kb?: boolean;
}) {
  return api<ApiHelpArticle>("/v1/help-articles", { method: "POST", orgScoped: true, body });
}

export function updateHelpArticle(id: string, body: Record<string, unknown>) {
  return api<ApiHelpArticle>(`/v1/help-articles/${id}`, { method: "PATCH", orgScoped: true, body });
}

export function deleteHelpArticle(id: string) {
  return api<void>(`/v1/help-articles/${id}`, { method: "DELETE", orgScoped: true });
}
