"use client";

import { api } from "./client";
import type { ApiOrg } from "./types";

export function listOrgs() {
  return api<ApiOrg[]>("/v1/orgs");
}

export function createOrg(name: string) {
  return api<ApiOrg>("/v1/orgs", { method: "POST", body: { name } });
}
