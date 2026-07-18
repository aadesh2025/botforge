# SESSION HANDOFF — BotForge

> **Read this first, then continue the build.** This file is the pick-up point for the next
> session. It records what's done, what's half-done, and exactly what to do next.

Last updated: **2026-07-19** · Latest commit: `phase-15-complete` · Branch: `master`

---

## 0. Before you do anything — read the docs fully

Read every file in `docs/` **in order** before writing code:

1. `../CLAUDE.md` (operating contract — autonomous build, Definition of Done, tech stack)
2. `00-README.md` → `01-PRD.md` → `02-ARCHITECTURE.md` → `03-DATABASE-SCHEMA.md`
3. `04-API-SPEC.md` → `05-FRONTEND.md` → `06-AI-ENGINE.md` → `07-INTEGRATIONS.md`
4. `09-DEPLOYMENT.md` → `10-TESTING.md`
5. `08-PHASES.md` ← **the build plan; execute phase by phase, in order**
6. Then the running logs: `PROGRESS.md` (per-phase status), `DECISIONS.md` (ADR-001…020),
   `ENV.md`, and `RUNBOOK-docker.md` (how to bring the stack up).

**Continue from where we left off: Phase 16 (Guardrails, moderation, hardening).**

---

## 1. What got done this session

A backend was built from nothing and the existing mock frontend was wired to it. The full
**auth → multi-tenant → LLM → agent-builder** vertical now works end-to-end, verified live.

- **Backend (FastAPI, `apps/api`, managed with `uv`):** system endpoints, auth, orgs/RBAC,
  the LLM provider layer, and agents + a streaming playground — all tested against **real
  Postgres** (transaction-rollback isolation). **61 tests pass; ruff + mypy strict clean.**
- **Infra:** `docker compose` (postgres+pgvector, redis, …), Alembic migrations applied for
  real, seed script, GitHub Actions CI (runs pg+redis+migrate+tests).
- **Frontend integration:** hand-written typed API client (`apps/web/src/lib/api/`) with
  Bearer + `X-Org-Id` + 401-refresh + an SSE reader; cookie token store; route-guard
  middleware; login/signup pages; `AuthGate`; org switcher, user menu, agents list, the
  **agent builder** (autosave + publish + real streaming playground), and credentials — all
  wired to the real API.
- **Verified live (Playwright):** signup → create-org → dashboard, login, agent create,
  autosave persisting across logout→login, publish → Live, playground streaming (echo fallback
  and graceful provider-error surfacing).
- **Two backend bugs found via the live test and fixed** (see `DECISIONS.md` ADR-020):
  streaming `ResponseNotRead`, and whitespace-only env keys treated as real.

---

## 2. Phase status (docs/08-PHASES.md — Phases 0–20)

| Phase | Title | Status |
|---|---|---|
| 0 | Repo/tooling/CI/compose | ✅ **complete** (tag `phase-00-complete`) |
| 1 | Database foundation | ✅ **complete** (tag `phase-01-complete`) |
| 2 | Auth & accounts | ✅ **complete** — backend + web auth pages (tag `phase-02-complete`) |
| 3 | Orgs & RBAC | ✅ **complete** — gap closed in Phase 15: members/invitations UI + real `lib/rbac` gating; viewer-denial verified live |
| 4 | App shell & design system | ✅ **complete** — shell + typed API client (tag `phase-04-complete`) |
| 5 | LLM provider layer | ✅ **complete** (tag `phase-05-complete`) |
| 6 | Agents & versions | ✅ **complete** — backend + builder wired + streaming playground (tag `phase-06-complete`) |
| 7 | Knowledge base & RAG | ✅ **complete** — backend (KB/ingestion/retrieval/RAG) + worker + UI wired; verified live (tag `phase-07-complete`) |
| 8 | Chat persistence & memory | ✅ **complete** — persistence + memory + WebSocket + conversations browser; branch-on-edit fix (tag `phase-08-complete`) |
| 9 | Tools & tool calling | ✅ **complete** — built-ins + HTTP tools + tool loop + tool_runs + Tools tab; live tool call via qwen3 (tag `phase-09-complete`) |
| 10 | n8n integration | ✅ **complete** — client + n8n tool type (sync/async) + automations UI; live agent→n8n verified (tag `phase-10-complete`) |
| 11 | Web widget | ✅ **complete** — public config/chat + Shadow-DOM widget + SDK + Channels tab; live embed verified (tag `phase-11-complete`) |
| 12 | Messaging channels | ✅ **complete** — Telegram/WhatsApp/Slack/Discord adapters + signed webhooks + Channels tab; Telegram inbound verified live (tag `phase-12-complete`) |
| 13 | Inbox & handoff | ✅ **complete** — handoff triggers + inbox + realtime hub + widget push; full loop verified live (tag `phase-13-complete`) |
| 14 | Analytics & metering | ✅ **complete** — live aggregates + rollups; verified against messages table (tag `phase-14-complete`) |
| 15 | API keys/webhooks/audit | ✅ **complete** — keys+auth, signed webhooks, audit, settings UIs; verified live (tag `phase-15-complete`) |
| 16 | **Guardrails & hardening** | ⬜ **NOT STARTED — do this next** |
| 17 | Admin console | ⬜ |
| 18 | Billing (optional) | ⬜ |
| 19 | E2E/docs/polish | ⬜ |
| 20 | Production deployment | ⬜ |

**Scoreboard:** 15 phases tagged complete (0–15 except 3 which is now ✅ too) · 0 partial · 5 not started (16–20).
Roughly **16 of 21** phases have real, tested, wired progress. **141 backend tests pass.**

### Backend business routes live now
`/v1/auth/*`, `/v1/orgs/*`, `/v1/credentials/*`, `/v1/agents/*` (+ playground + `/chat` +
`/chat/ws`), `/v1/knowledge/*`, `/v1/conversations/*`, `/v1/tools/*` (+ `/n8n/*`),
`/v1/public/agents/{public_key}/{config,chat,ws,subscribe}`, `/v1/channels/*`, `/v1/inbox/*` (+ WS),
`/v1/analytics/*`, `/v1/apikeys/*`, `/v1/webhooks/*`, `/v1/audit`. **API-key auth** works on any
org-scoped route (`X-API-Key` / `Bearer bf_…`). Not built yet: admin console, billing.

### Frontend: what's real vs mock
- **Real (wired to API):** login/signup, org switcher, user menu, agents + builder (all tabs),
  credentials, knowledge, **conversations**, **automations**, **inbox**, **analytics** + dashboard
  stats, **settings** (org members/invites, API keys, webhooks, audit) with real RBAC gating.
  The **web widget is real** (`packages/widget` → `/widget.js`).
- **Still mock:** the `/admin` console (Phase 17) and billing (Phase 18).

---

## 3. NEXT: Phase 16 — Guardrails, moderation, hardening

Per `08-PHASES.md §16`:
- **16.1** Guardrails: blocked topics (already in `version.persona.blockedTopics`), prompt-injection
  heuristics on **untrusted** content (retrieved RAG chunks + tool outputs — never let them
  override the system prompt), and an output redaction hook. Wire into `app/chat` assembly/runtime.
- **16.2** Security pass: rate limits on every public surface (public chat is limited; add to
  channel webhooks?), SSRF guards (present for HTTP tools/webhooks/URL-KB — audit coverage),
  CSP/security headers (add middleware), encrypted-key audit, input/file validation review →
  write `docs/SECURITY.md` checklist.
- **16.3** Load/perf sanity (locust/k6) against NFR-1 (p50 first-token on Groq).

Reuse: `app/chat/assembly.build_messages` is where retrieved context + memory + history are
assembled — the guardrail input filter goes there. `app/rag/loaders._is_blocked_host` is the
shared SSRF check. The rate limiter is `app/core/ratelimit`.

### Roadmap items now due before Phase 20 (see PROGRESS roadmap)
- **Realtime hub → Redis pub/sub** (ADR-028): in-process only; must swap before multi-node prod.
- **Webhook retry beat sweep**: `pending` deliveries past `next_retry_at` need a periodic sweep.

### Live-demo state (carried forward)
- **API keys / webhooks / audit / RBAC verified live** this session (see PROGRESS §15). A viewer
  member `viewer_demo@example.com` exists in the demo org (role viewer) for RBAC demos.
- **Analytics verified live** against the messages table (real Groq usage from prior phases).
- **Groq key is now VALID** — real chat works (`llama-3.1-8b-instant` verified). SECRET_KEY was
  rotated: old JWTs + any Fernet-encrypted `provider_credentials`/channel tokens are invalid;
  re-login and re-enter provider keys if needed (env Groq key is used as the fallback).
- **Memory summarization verified real** (llama-3.1-8b-instant), not fake.
- **n8n live**: `BotForge — Echo (sync)` workflow active (`/webhook/botforge-echo`); "aadesh"
  agent (`019f7098-…`, qwen3:14b) has it bound + `calculator`. n8n API key valid.
- **Channels**: verified via signed inbound → real bot → persist (Telegram inbound live gave a
  real Groq "Paris."). Provider *delivery* (telegram.org etc.) is unreachable from this env, so
  outbound is mock-tested; `TELEGRAM_BOT_TOKEN` is present. Tokens are per-`Channel` (encrypted).
- **Handoff/inbox verified live** in the browser (widget → handoff → inbox takeover → operator
  reply pushed to the widget → handback → bot resumes). Realtime is an **in-process** hub
  (`app/realtime/hub`) — single-node only; swap for Redis pub/sub to scale out.
- **qwen3:14b** does tool calls over Ollama (local, key-free, slow 30–90s/turn).
- **Chat vs playground:** `/v1/agents/{id}/chat` persists + uses the live version; the builder
  playground is ephemeral. Widget/channel chat sets `channel=<type>`.
- `widget-demo.html` is committed with a `YOUR_PUBLIC_KEY` placeholder; rebuild the widget with
  `cd packages/widget && node build.mjs`.

---

## 4. How to bring the stack back up (see RUNBOOK-docker.md for detail)

```
# 1. Docker Desktop must be running, then:
cd infra && docker compose up -d postgres redis          # wait for healthy
# 2. Migrate (only if schema changed) + optionally seed:
cd ../apps/api && uv run alembic upgrade head
# 3. Run the API on the host (fast path):
uv run uvicorn app.main:app --port 8000                  # /readyz should be green
# 3b. Run the Celery worker (REQUIRED for document ingestion; --pool=solo on Windows):
uv run celery -A app.worker.celery_app worker --pool=solo --loglevel=info
# 4. Run the web app:
cd ../web && npm run dev                                 # grabs a free port (3000/3001/…)
```
Dev CORS accepts any `http://localhost:<port>`. A demo account exists from this session:
`webflow_test@example.com` / `password123` (org "Aurozen Live"). Agents: "Support Concierge"
(published) and "aadesh" (draft, wired to Ollama qwen3:14b + the "Product Docs" KB for RAG).
Ingestion uses Ollama `nomic-embed-text` (already pulled in the local Ollama). The web dev
server from this session is on **:3001** (port 3000 is taken by another local app).

---

## 5. Conventions to keep following (don't reinvent)

- **Definition of Done** (CLAUDE.md §2): compiles, lints, tests pass, committed, env documented.
- **New backend module** = `app/modules/<name>/{schemas,service,router}.py`; depend on
  `current_org` (X-Org-Id) + `require_permission(ctx.role, PERM)` (constants in `core/rbac.py`).
- **DB-backed tests** = real Postgres + transaction rollback (`conftest` overrides `get_session`,
  no commit); services never call `commit`.
- **Async ORM gotcha:** never use server-side `onupdate=func.now()` on attributes you read
  during response serialization → use Python-side defaults (see `TimestampMixin`).
- Keep `PROGRESS.md` + `DECISIONS.md` current after every phase; `git tag phase-NN-complete`.
- **Prod TODO:** move web auth tokens to httpOnly cookies via a Next route handler.

---

**Pick up here:** read the docs (§0), bring the stack up (§4), then start **Phase 7** (§3).
