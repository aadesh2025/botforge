import { NextRequest, NextResponse } from "next/server";
import { clearRefreshCookie, forward, REFRESH_COOKIE, setRefreshCookie } from "../_bff";

// POST /api/auth/refresh → reads the httpOnly refresh cookie, rotates it against the API, and
// returns a fresh access token. The client never sees or handles the refresh token.
export async function POST(request: NextRequest) {
  const refresh = request.cookies.get(REFRESH_COOKIE)?.value;
  if (!refresh) {
    return NextResponse.json({ error: { code: "auth.no_session", message: "No session" } }, { status: 401 });
  }
  const { status, data } = await forward("/v1/auth/refresh", { refresh_token: refresh });
  if (status >= 400 || !data || typeof data !== "object") {
    const res = NextResponse.json({ error: { code: "auth.refresh_failed", message: "Refresh failed" } }, { status: 401 });
    clearRefreshCookie(res); // stale/rotated refresh — drop it
    return res;
  }
  const { access_token, refresh_token } = data as { access_token: string; refresh_token: string };
  const res = NextResponse.json({ access_token });
  setRefreshCookie(res, refresh_token); // rotation: store the new refresh token
  return res;
}
