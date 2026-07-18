"use client";

import { api } from "./client";
import { API_BASE } from "./config";
import { getAccessToken, getActiveOrgId } from "./tokens";
import type { ApiMessage } from "./conversations";

export interface ApiHandoff {
  id: string;
  status: string;
  requested_by: string;
  reason: string | null;
  assigned_to: string | null;
  notes: { by: string; text: string; at: string }[];
  tags: string[];
  created_at: string;
  resolved_at: string | null;
}

export interface ApiInboxItem {
  id: string;
  agent_id: string;
  channel: string;
  status: string;
  title: string | null;
  channel_user_id: string | null;
  message_count: number;
  last_message_at: string | null;
  created_at: string;
  handoff: ApiHandoff | null;
}

export interface ApiInboxDetail extends ApiInboxItem {
  messages: ApiMessage[];
}

export function listInbox(status?: string) {
  const q = status ? `?status=${status}` : "";
  return api<ApiInboxItem[]>(`/v1/inbox/conversations${q}`, { orgScoped: true });
}

export function getInboxDetail(cid: string) {
  return api<ApiInboxDetail>(`/v1/inbox/conversations/${cid}`, { orgScoped: true });
}

export function takeover(cid: string) {
  return api<ApiInboxItem>(`/v1/inbox/conversations/${cid}/takeover`, { method: "POST", orgScoped: true });
}

export function handback(cid: string) {
  return api<ApiInboxItem>(`/v1/inbox/conversations/${cid}/handback`, { method: "POST", orgScoped: true });
}

export function closeConversation(cid: string) {
  return api<ApiInboxItem>(`/v1/inbox/conversations/${cid}/close`, { method: "POST", orgScoped: true });
}

export function replyInbox(cid: string, text: string) {
  return api<ApiMessage>(`/v1/inbox/conversations/${cid}/messages`, {
    method: "POST",
    orgScoped: true,
    body: { text },
  });
}

export function setTags(cid: string, tags: string[]) {
  return api<ApiHandoff>(`/v1/inbox/conversations/${cid}/tags`, { method: "POST", orgScoped: true, body: { tags } });
}

export function addNote(cid: string, text: string) {
  return api<ApiHandoff>(`/v1/inbox/conversations/${cid}/notes`, { method: "POST", orgScoped: true, body: { text } });
}

/** Open the operator inbox realtime stream. Returns the WebSocket (or null if not authed). */
export function openInboxSocket(): WebSocket | null {
  const token = getAccessToken();
  const org = getActiveOrgId();
  if (!token || !org) return null;
  const wsBase = API_BASE.replace(/^http/, "ws");
  return new WebSocket(`${wsBase}/v1/inbox/ws?token=${encodeURIComponent(token)}&org_id=${org}`);
}
