"use client";

import { api, ApiError } from "./client";
import { clearAuth, setAccessToken } from "./tokens";
import type { AuthResponse, MeResponse } from "./types";

// Auth goes through the same-origin Next BFF (`/api/auth/*`) so the refresh token is stored in
// an httpOnly cookie the browser JS can't read. Only the access token comes back to the client.

async function bff<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const err = (data as { error?: { code?: string; message?: string } })?.error;
    throw new ApiError(res.status, err?.code ?? "auth.error", err?.message ?? "Authentication failed");
  }
  return data as T;
}

export async function signup(email: string, password: string, fullName?: string) {
  const res = await bff<AuthResponse>("/api/auth/signup", { email, password, full_name: fullName });
  setAccessToken(res.access_token);
  return res;
}

export async function login(email: string, password: string) {
  const res = await bff<AuthResponse>("/api/auth/login", { email, password });
  setAccessToken(res.access_token);
  return res;
}

export async function me() {
  return api<MeResponse>("/v1/auth/me");
}

export async function logout() {
  try {
    await bff("/api/auth/logout");
  } finally {
    clearAuth();
  }
}
