"use client";

import { api } from "./client";
import { clearAuth, getRefreshToken, setTokens } from "./tokens";
import type { AuthResponse, MeResponse } from "./types";

export async function signup(email: string, password: string, fullName?: string) {
  const res = await api<AuthResponse>("/v1/auth/signup", {
    method: "POST",
    body: { email, password, full_name: fullName },
  });
  setTokens(res.access_token, res.refresh_token);
  return res;
}

export async function login(email: string, password: string) {
  const res = await api<AuthResponse>("/v1/auth/login", {
    method: "POST",
    body: { email, password },
  });
  setTokens(res.access_token, res.refresh_token);
  return res;
}

export async function me() {
  return api<MeResponse>("/v1/auth/me");
}

export async function logout() {
  const refresh_token = getRefreshToken();
  try {
    await api("/v1/auth/logout", { method: "POST", body: { refresh_token } });
  } finally {
    clearAuth();
  }
}
