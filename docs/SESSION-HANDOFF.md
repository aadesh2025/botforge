# SESSION HANDOFF — BotForge

> **Read this first, then continue the build.** This file is the pick-up point for the next
> session. It records what's done, what's half-done, and exactly what to do next.

Last updated: **2026-07-18** · Latest commit: `phase-13-complete` · Branch: `master`

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

**Continue from where we left off: Phase 14 (Analytics & usage metering).**

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
| 3 | Orgs & RBAC | 🟨 **mostly done** — backend ✅, org switcher wired; **members/invitations settings UI + RoleGuard still on mocks** |
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
| 14 | **Analytics & metering** | ⬜ **NOT STARTED — do this next** (analytics UI is mock) |
| 15 | API keys/webhooks/audit | ⬜ (settings pages are mock) |
| 16 | Guardrails & hardening | ⬜ |
| 17 | Admin console | ⬜ |
| 18 | Billing (optional) | ⬜ |
| 19 | E2E/docs/polish | ⬜ |
| 20 | Production deployment | ⬜ |

**Scoreboard:** 13 phases tagged complete (0,1,2,4,5,6,7,8,9,10,11,12,13) · 1 mostly done (3) · 7 not started (14–20).
Roughly **13 of 21** phases have real, tested, wired progress. **123 backend tests pass.**

### Backend business routes live now
`/v1/auth/*`, `/v1/orgs/*`, `/v1/credentials/*`, `/v1/agents/*` (+ playground + `/chat` +
`/chat/ws`), `/v1/knowledge/*`, `/v1/conversations/*`, `/v1/tools/*` (+ `/n8n/*`),
`/v1/public/agents/{public_key}/{config,chat,ws,subscribe}`, `/v1/channels/*` (+ signed webhooks),
`/v1/inbox/*` (+ WS). Not built yet: analytics, apikeys, webhooks (outbound), admin, billing.

### Frontend: what's real vs mock
- **Real (wired to API):** login/signup, org switcher, user menu, agents list + builder
  (Persona/Model/Versions/**Knowledge**/**Tools**/**Channels** + playground), credentials,
  knowledge, **conversations browser**, **automations** (n8n bind), **inbox** (two-pane, realtime).
- **Still mock (no backend yet):** dashboard analytics, analytics, and members/invites settings.
  The **web widget is real** (`packages/widget` → `/widget.js`).

---

## 3. NEXT: Phase 14 — Analytics & usage metering

Per `08-PHASES.md §14` and `04-API-SPEC.md §Analytics`:
- **14.1** Usage rollups (Celery) into `usage_records`; quotas + threshold events. The raw data
  already exists: every `messages` row carries `tokens_prompt/completion`, `cost_micros`,
  `latency_ms`, `provider`, `model`; `tool_runs` carries per-tool latency/status.
- **14.2** Analytics endpoints: overview (conversations/messages/users/resolution+handoff rate),
  usage (tokens + cost, group by day/provider/model), latency, top/unanswered questions, CSV export.
- **14.3** Analytics dashboards (cards + Recharts + date range + export) — the `/analytics` and
  dashboard pages are still mock.

Reuse: aggregate straight off `messages`/`conversations`/`handoffs`/`tool_runs` (all org-scoped).
"Resolution rate" ≈ conversations closed without an open handoff; "handoff rate" ≈ conversations
with a `Handoff` row. "Unanswered" ≈ turns where RAG returned no citations (a marker could be
added). The Celery worker + `usage_records`/`quotas` tables already exist (Phase 1/7).

### Live-demo state (carried forward)
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
