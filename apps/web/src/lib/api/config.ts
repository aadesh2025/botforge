export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") || "http://localhost:8000";

// Cookie names shared by the client and the middleware guard.
export const COOKIE = {
  access: "bf_access",
  refresh: "bf_refresh",
  org: "bf_org",
} as const;
