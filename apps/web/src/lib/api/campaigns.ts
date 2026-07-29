"use client";

import { api } from "./client";

export type CampaignKind = "widget_trigger" | "broadcast";
export type CampaignStatus = "draft" | "active" | "paused";

export interface ApiCampaign {
  id: string;
  agent_id: string;
  kind: CampaignKind;
  name: string;
  message: string;
  trigger_config: { delay_seconds?: number; url_pattern?: string };
  status: CampaignStatus;
  created_at: string;
  updated_at: string;
}

export function listCampaigns(agentId?: string) {
  const qs = agentId ? `?agent_id=${agentId}` : "";
  return api<ApiCampaign[]>(`/v1/campaigns${qs}`, { orgScoped: true });
}

export function createCampaign(body: {
  agent_id: string;
  kind?: CampaignKind;
  name: string;
  message: string;
  trigger_config?: Record<string, unknown>;
  status?: CampaignStatus;
}) {
  return api<ApiCampaign>("/v1/campaigns", { method: "POST", orgScoped: true, body });
}

export function updateCampaign(id: string, body: Record<string, unknown>) {
  return api<ApiCampaign>(`/v1/campaigns/${id}`, { method: "PATCH", orgScoped: true, body });
}

export function deleteCampaign(id: string) {
  return api<void>(`/v1/campaigns/${id}`, { method: "DELETE", orgScoped: true });
}
