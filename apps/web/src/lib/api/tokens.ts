"use client";

import { COOKIE } from "./config";

// Cookie-backed token storage. Non-httpOnly so the SPA can read them and the
// middleware can gate routes. For production, move to httpOnly cookies set by a
// Next route handler (see docs/05 §1).

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
export function getRefreshToken() {
  return getCookie(COOKIE.refresh);
}
export function getActiveOrgId() {
  return getCookie(COOKIE.org);
}

export function setTokens(access: string, refresh: string) {
  setCookie(COOKIE.access, access, 60 * 30); // access ~30m window on the client
  setCookie(COOKIE.refresh, refresh, 60 * 60 * 24 * 30);
}

export function setActiveOrgId(orgId: string) {
  setCookie(COOKIE.org, orgId, 60 * 60 * 24 * 30);
}

export function clearAuth() {
  delCookie(COOKIE.access);
  delCookie(COOKIE.refresh);
  delCookie(COOKIE.org);
}
