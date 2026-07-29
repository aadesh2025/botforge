"use client";

import { api } from "./client";

/** A deliberately short, ordered funnel — free text would fragment the filter. */
export const LEAD_STAGES = ["new", "contacted", "qualified", "customer", "lost"] as const;
export type LeadStage = (typeof LEAD_STAGES)[number];

export interface ApiCrmContact {
  id: string;
  channel: string;
  external_id: string;
  display_name: string | null;
  avatar_url: string | null;
  lead_stage: LeadStage | null;
  order_status: string | null;
  labels: string[];
  extra: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  last_active_at: string | null;
  conversation_count: number;
}

export interface ApiContactNote {
  by: string;
  text: string;
  at: string;
}

export interface ApiContactConversation {
  id: string;
  agent_id: string;
  channel: string;
  status: string;
  title: string | null;
  last_message_at: string | null;
  created_at: string;
}

export interface ApiContactDetail extends ApiCrmContact {
  notes: ApiContactNote[];
  conversations: ApiContactConversation[];
}

export interface ContactListResult {
  items: ApiCrmContact[];
  total: number;
  limit: number;
  offset: number;
}

export interface ContactFilters {
  q?: string;
  lead_stage?: string;
  channel?: string;
  label?: string;
  limit?: number;
  offset?: number;
}

export function listContacts(filters: ContactFilters = {}) {
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(filters)) {
    if (v !== undefined && v !== "" && v !== null) params.set(k, String(v));
  }
  const qs = params.size ? `?${params}` : "";
  return api<ContactListResult>(`/v1/contacts${qs}`, { orgScoped: true });
}

/** Add a contact by hand. Everything else in this table arrives via a message. */
export function createContact(body: {
  display_name: string;
  email?: string | null;
  phone?: string | null;
  lead_stage?: string | null;
  order_status?: string | null;
}) {
  return api<ApiContactDetail>("/v1/contacts", { method: "POST", orgScoped: true, body });
}

export function getContact(id: string) {
  return api<ApiContactDetail>(`/v1/contacts/${id}`, { orgScoped: true });
}

export function updateContact(
  id: string,
  body: { lead_stage?: string | null; order_status?: string | null; display_name?: string },
) {
  return api<ApiContactDetail>(`/v1/contacts/${id}`, { method: "PATCH", orgScoped: true, body });
}

export function setContactLabels(id: string, labels: string[]) {
  return api<ApiContactDetail>(`/v1/contacts/${id}/labels`, {
    method: "PATCH",
    orgScoped: true,
    body: { labels },
  });
}

export function addContactNote(id: string, text: string) {
  return api<ApiContactDetail>(`/v1/contacts/${id}/notes`, {
    method: "POST",
    orgScoped: true,
    body: { text },
  });
}
