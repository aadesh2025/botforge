# SESSION HANDOFF — BotForge

> **Read this first, then continue the build.** This file is the pick-up point for the next
> session. It records what's done, what's half-done, and exactly what to do next.

Last updated: **2026-07-18** · Latest commit: `phase-09-complete` · Branch: `master`

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

**Continue from where we left off: Phase 10 (n8n integration).**

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
| 10 | **n8n integration** | ⬜ **NOT STARTED — do this next** (Automations page is mock) |
| 11 | Web widget | ⬜ (widget preview is mock) |
| 12 | Messaging channels | ⬜ (Channels tab is mock) |
| 13 | Inbox & handoff | ⬜ (inbox UI is mock) |
| 14 | Analytics & metering | ⬜ (analytics UI is mock) |
| 15 | API keys/webhooks/audit | ⬜ (settings pages are mock) |
| 16 | Guardrails & hardening | ⬜ |
| 17 | Admin console | ⬜ |
| 18 | Billing (optional) | ⬜ |
| 19 | E2E/docs/polish | ⬜ |
| 20 | Production deployment | ⬜ |

**Scoreboard:** 9 phases tagged complete (0,1,2,4,5,6,7,8,9) · 1 mostly done (3) · 11 not started (10–20).
Roughly **9 of 21** phases have real, tested, wired progress.

### Backend business routes live now
`/v1/auth/*`, `/v1/orgs/*`, `/v1/credentials/*`, `/v1/agents/*` (+ playground + `/chat` +
`/chat/ws`), `/v1/knowledge/*`, `/v1/conversations/*`, `/v1/tools/*`. Everything else in
`04-API-SPEC.md` is not built yet (channels, inbox, analytics, apikeys, webhooks, admin, billing).

### Frontend: what's real vs mock
- **Real (wired to API):** login/signup, org switcher, user menu, agents list + builder
  (Persona/Model/Versions/**Knowledge**/**Tools** + playground), credentials settings, knowledge
  list + detail, **conversations browser** (persisted streaming chat).
- **Still mock (no backend yet):** dashboard analytics, inbox, analytics, automations, the
  builder's Channels tab, and members/invites settings.

---

## 3. NEXT: Phase 10 — n8n integration

Per `08-PHASES.md §10` and `07-INTEGRATIONS.md`:
- **10.1** `integrations/n8n_client` (list workflows, trigger webhook signed, verify callback).
  n8n is already in compose; `N8N_BASE_URL` / `N8N_API_KEY` in env (stub loudly if unset).
- **10.2** n8n tool type: bind a workflow → callable tool (sync + async modes + callback
  endpoint). This slots into the **existing tool system** (`app/tools`): add a `type="n8n"`
  branch in `tools.service._dispatch` + an `n8n` executor, mirroring the `http` tool. The
  tool-calling loop (`run_turn`) already handles it.
- **10.3** Ship starter workflows in `infra/n8n/` + import docs.
- **10.4** `/automations` page (currently mock): list n8n workflows, bind as tools.

### Phase 8/9 gotchas & live-demo state
- **Tools live-verified** on the "aadesh" draft agent (`019f7098-…`, Ollama `qwen3:14b`): tools
  enabled + `calculator` built-in attached; asking "47 × 89" makes it call the tool → `4183`.
  That agent currently has tools on and RAG off. The "Product Docs" KB (`019f7164-…`) is still
  attached-capable for RAG demos.
- **qwen3:14b supports tool calls** over Ollama's OpenAI-compatible endpoint — good for local,
  key-free live tool demos (but slow: a turn can take 30–90s).
- **Chat vs playground:** `/v1/agents/{id}/chat` persists (backs the conversations browser) and
  uses the **live** version (published `current_version_id` else latest draft); the builder
  playground stays ephemeral and uses the latest draft.
- **Summarizer** never uses the agent's model — it's `SUMMARY_PROVIDER/MODEL` (groq→fake).
- The dev **GROQ_API_KEY in `.env` is invalid** (401) — real chat against groq fails; use Ollama
  or the fake provider for live demos until a valid key is added.

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
