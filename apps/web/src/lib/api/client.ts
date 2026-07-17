"use client";

import { API_BASE } from "./config";
import { clearAuth, getAccessToken, getActiveOrgId, getRefreshToken, setTokens } from "./tokens";

export class ApiError extends Error {
  code: string;
  status: number;
  details?: unknown;
  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  orgScoped?: boolean; // attach the X-Org-Id header
  signal?: AbortSignal;
}

async function toError(res: Response): Promise<ApiError> {
  let code = "http_error";
  let message = res.statusText;
  let details: unknown;
  try {
    const data = await res.json();
    if (data?.error) {
      code = data.error.code ?? code;
      message = data.error.message ?? message;
      details = data.error.details;
    }
  } catch {
    /* non-JSON body */
  }
  return new ApiError(res.status, code, message, details);
}

let refreshing: Promise<boolean> | null = null;

async function tryRefresh(): Promise<boolean> {
  const refresh = getRefreshToken();
  if (!refresh) return false;
  if (!refreshing) {
    refreshing = (async () => {
      try {
        const res = await fetch(`${API_BASE}/v1/auth/refresh`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: refresh }),
        });
        if (!res.ok) {
          clearAuth();
          return false;
        }
        const data = await res.json();
        setTokens(data.access_token, data.refresh_token);
        return true;
      } finally {
        refreshing = null;
      }
    })();
  }
  return refreshing;
}

function buildHeaders(orgScoped?: boolean): Record<string, string> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const token = getAccessToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (orgScoped) {
    const orgId = getActiveOrgId();
    if (orgId) headers["X-Org-Id"] = orgId;
  }
  return headers;
}

export async function api<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, orgScoped, signal } = opts;
  const init: RequestInit = {
    method,
    headers: buildHeaders(orgScoped),
    body: body !== undefined ? JSON.stringify(body) : undefined,
    signal,
  };

  let res = await fetch(`${API_BASE}${path}`, init);
  if (res.status === 401 && getRefreshToken()) {
    if (await tryRefresh()) {
      init.headers = buildHeaders(orgScoped);
      res = await fetch(`${API_BASE}${path}`, init);
    }
  }
  if (!res.ok) throw await toError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

/** Open an SSE stream (used by the playground). Yields parsed data objects. */
export async function* apiStream(
  path: string,
  body: unknown,
  signal?: AbortSignal,
): AsyncGenerator<Record<string, unknown>> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: buildHeaders(true),
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok || !res.body) throw await toError(res);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";
    for (const part of parts) {
      const line = part.trim();
      if (!line.startsWith("data:")) continue;
      const payload = line.slice(5).trim();
      if (!payload || payload === "[DONE]") continue;
      try {
        yield JSON.parse(payload);
      } catch {
        /* skip malformed chunk */
      }
    }
  }
}
