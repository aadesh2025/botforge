# SECURITY.md — BotForge security checklist

> Verified during **Phase 16.2** (2026-07-19). Each item is marked ✅ met, ⚠️ partial, or
> ❌ unmet with a note. This is a living checklist — re-verify at each release.

## 1. Authentication & sessions
- ✅ **Password hashing**: argon2 (`argon2-cffi`) — see `app/core/security.py`.
- ✅ **JWT access + refresh**: HS256 signed with `SECRET_KEY`. We do **not** use asymmetric/ECDSA
  JWTs (see the `ecdsa` advisory in §8).
- ✅ **Magic links / OAuth**: tokens are single-use / signed; provider secrets read from env only.
- ⚠️ **Web token storage**: the Next.js client stores the access token in a **JS-readable cookie**,
  not `httpOnly`. Moving to httpOnly (via a Next route-handler BFF proxy) is **deferred** — tracked
  as required prod hardening (ADR-019, PROGRESS roadmap). Mitigations in place: short access-token
  TTL + refresh rotation, strict CORS, and the API never reflects tokens.

## 2. Authorization & multi-tenancy
- ✅ **Tenant isolation**: every org-scoped query is filtered by `organization_id`; org resolved via
  `current_org` / `org_context` (`app/modules/orgs/deps.py`).
- ✅ **RBAC matrix**: owner/admin/editor/viewer/operator enforced by `require_permission`
  (`app/core/rbac.py`), on both API and UI. Viewer-denial verified live (Phase 15).
- ✅ **API-key scope enforcement** (Phase 16.2): keys carry `read`/`write`/`admin` scopes. A key's
  effective role = its scope tier **capped by the creating member's role** (least privilege). `admin`
  scope maps to the `admin` role, never `owner`, so a key can never delete the org. Verified live: a
  read-scoped key gets **403 on a write endpoint**. Org-admin routes are JWT-only (path-scoped
  `org_context`), so API keys cannot manage members at all.

## 3. Input validation & injection
- ✅ **Request validation**: Pydantic v2 schemas on every request/response.
- ✅ **SQL injection**: SQLAlchemy 2.0 parametrized queries only; no string-built SQL.
- ✅ **Prompt injection** (Phase 16.1): retrieved RAG chunks and tool output are treated as **data,
  not instructions** — neutralized (`app/chat/guardrails.neutralize_injections`) and wrapped with an
  explicit data directive before reaching the model. Blocked-topics refuse pre-LLM.
- ✅ **Output redaction** (Phase 16.1): secret-looking strings (API keys, cards) are redacted from
  assistant output before it is stored/returned.

## 4. SSRF
- ✅ **Coverage**: the shared guard `app/rag/loaders._is_blocked_host` (rejects loopback / private /
  link-local / reserved / multicast, resolved via DNS) is applied to **all** user-controlled outbound
  fetches: URL knowledge ingestion (`rag/loaders`), the HTTP tool (`tools/http_tool`), the
  `http_request` builtin (`tools/builtins`), and **outbound webhook delivery** (`webhooks/dispatch`).
- ✅ **n8n exemption is deliberate & documented**: `app/integrations/n8n_client` targets the
  operator-configured, trusted `N8N_BASE_URL` (loopback in dev), not arbitrary user input, so it is
  intentionally not SSRF-guarded (noted in the module docstring).

## 5. Rate limiting (public surfaces)
- ✅ **Auth**: signup / login / resend / forgot / magic (`app/modules/auth/router.py`).
- ✅ **Public chat**: `/v1/public/agents/{key}/chat` (60/min).
- ✅ **Channel webhooks** (Phase 16.2): telegram / whatsapp / slack / discord inbound (120/min per IP).
- ✅ **n8n callback** (Phase 16.2): `/v1/tools/n8n/callback` (120/min per IP).
- Backed by Redis fixed-window with an in-memory fallback (`app/core/ratelimit.py`).

## 6. Secrets & data at rest
- ✅ **Provider credentials + channel tokens encrypted at rest** with Fernet (key derived from
  `SECRET_KEY`); masked in API responses, revealed once on create.
- ✅ **API keys** stored as sha256 hashes + a lookup prefix; the full key is shown once.
- ✅ **Webhook signing secrets** encrypted at rest; deliveries HMAC-SHA256 signed over
  `"{timestamp}.{body}"`.
- ✅ **No secrets logged**: structured logging; secrets never included in log events.

## 7. Transport & headers
- ✅ **Security headers middleware** (Phase 16.2, `SecurityHeadersMiddleware`): `X-Content-Type-Options:
  nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Cross-Origin-Opener-Policy`,
  `Cross-Origin-Resource-Policy`, `Permissions-Policy`, and a strict API CSP
  (`default-src 'none'; frame-ancestors 'none'; base-uri 'none'`). Docs UIs (`/docs`, `/redoc`) are
  exempted from CSP/X-Frame-Options so Swagger/ReDoc render.
- ✅ **HSTS** emitted in production only (`Strict-Transport-Security`, 2 years, includeSubDomains).
- ✅ **CORS**: explicit allow-list in prod; localhost-any only in dev.
- ⚠️ **TLS termination**: handled by the reverse proxy (Nginx/Caddy) at deploy — verify at Phase 20.

## 8. Dependency audit (wired into CI — `security` job)
Advisory (non-blocking) `pip-audit` + `npm audit` run in CI. Results as of 2026-07-19:
- ⚠️ **Python — `ecdsa 0.19.2` (PYSEC-2026-1325, no fix available)**: transitive via `python-jose`.
  **Not exploitable in our config** — we sign JWTs with HS256 (symmetric) and perform no ECDSA
  operations. Follow-up: migrate JWT handling to `PyJWT`/`authlib` to drop `python-jose`/`ecdsa`.
- ❌ **Web — 5 advisories (4 high, 1 moderate) in Next.js 14 + bundled postcss**: Image-Optimization
  DoS, WebSocket-upgrade SSRF, RSC cache poisoning, i18n middleware bypass, postcss stringify XSS. The
  fix requires a **Next.js 14 → 16 major upgrade** (breaking). **Deferred to Phase 19/20** to avoid
  destabilizing the app mid-build. Partial applicability: we don't use i18n; realtime WS runs on the
  FastAPI backend, not Next; image optimization is minimal. Tracked in the PROGRESS roadmap.

## 9. Known gaps / follow-ups (tracked in PROGRESS roadmap)
- httpOnly cookie migration for web auth tokens (§1).
- Next.js major upgrade to clear the web advisories (§8).
- Realtime hub → Redis pub/sub before multi-node prod (ADR-028).
- Webhook retry beat-sweep for `pending` deliveries past `next_retry_at`.
- Replace `python-jose` to drop the `ecdsa` advisory (§8).
