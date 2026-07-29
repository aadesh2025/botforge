"use client";

import { api } from "./client";

export type MacroActionType = "reply" | "add_tag" | "assign" | "resolve";

export interface MacroAction {
  type: MacroActionType;
  params: Record<string, string>;
}

export interface ApiMacro {
  id: string;
  name: string;
  actions: MacroAction[];
  created_at: string;
  updated_at: string;
}

export interface MacroRunResult {
  macro_id: string;
  conversation_id: string;
  applied: MacroActionType[];
}

export function listMacros() {
  return api<ApiMacro[]>("/v1/macros", { orgScoped: true });
}

export function createMacro(name: string, actions: MacroAction[]) {
  return api<ApiMacro>("/v1/macros", { method: "POST", orgScoped: true, body: { name, actions } });
}

export function updateMacro(id: string, body: { name?: string; actions?: MacroAction[] }) {
  return api<ApiMacro>(`/v1/macros/${id}`, { method: "PATCH", orgScoped: true, body });
}

export function deleteMacro(id: string) {
  return api<void>(`/v1/macros/${id}`, { method: "DELETE", orgScoped: true });
}

/** Run every action in order against one conversation — all of them, or none. */
export function runMacro(cid: string, macroId: string) {
  return api<MacroRunResult>(`/v1/inbox/conversations/${cid}/macros/${macroId}`, {
    method: "POST",
    orgScoped: true,
  });
}
