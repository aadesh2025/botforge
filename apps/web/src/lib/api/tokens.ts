"use client";

import { COOKIE } from "./config";

// Client-side token storage. The long-lived REFRESH token is NOT here — it lives in an
// httpOnly cookie set by the Next BFF (`/api/auth/*`), unreadable by JS. Only the short-lived
// access token + active org are kept as JS-readable cookies, because the cross-origin API
// calls, SSE streams, and the operator-inbox WebSocket (`?token=`) all need the access token
// in JS. See docs/SECURITY.md §1 / ADR-019.

function setCookie(name: string, value: string, maxAgeSec: number) {
  if (typeof document === "undefined") return;
  document.cookie = `${name}=${encodeURIComponent(value)}; path=/; max-age=${maxAgeSec}; samesite=lax`;
}

function getCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

function delCookie(name: string) {
  if (typeof document === "undefined") return;
  document.cookie = `${name}=; path=/; max-age=0`;
}

export function getAccessToken() {
  return getCookie(COOKIE.access);
}
export function getActiveOrgId() {
  return getCookie(COOKIE.org);
}

export function setAccessToken(access: string) {
  setCookie(COOKIE.access, access, 60 * 30); // ~30m client window; rotated via the BFF refresh
}

export function setActiveOrgId(orgId: string) {
  setCookie(COOKIE.org, orgId, 60 * 60 * 24 * 30);
}

export function clearAuth() {
  delCookie(COOKIE.access);
  delCookie(COOKIE.org);
  // The httpOnly refresh cookie is cleared server-side by POST /api/auth/logout.
}
