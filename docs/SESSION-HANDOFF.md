# SESSION HANDOFF — BotForge

> **Read this first, then continue the build.** This file is the pick-up point for the next
> session. It records what's done, what's half-done, and exactly what to do next.

Last updated: **2026-07-17** · Latest commit: `b2cb207` · Branch: `master`

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

**Continue from where we left off: Phase 7 (Knowledge base & RAG).**

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
| 7 | **Knowledge base & RAG** | ⬜ **NOT STARTED — do this next** |
| 8 | Chat persistence & memory | ⬜ |
| 9 | Tools & tool calling | ⬜ (builder Tools tab is mock) |
| 10 | n8n integration | ⬜ (Automations page is mock) |
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

**Scoreboard:** 6 phases tagged complete (0,1,2,4,5,6) · 1 mostly done (3) · 14 not started (7–20).
Roughly **6 of 21** phases have real, tested, wired progress.

### Backend business routes live now
`/v1/auth/*`, `/v1/orgs/*`, `/v1/credentials/*`, `/v1/agents/*` (+ playground). Everything
else in `04-API-SPEC.md` is not built yet.

### Frontend: what's real vs mock
- **Real (wired to API):** login/signup, org switcher, user menu, agents list + builder
  (Persona/Model/Versions + playground), credentials settings.
- **Still mock (no backend yet):** dashboard analytics, knowledge, inbox, analytics,
  automations, the builder's Knowledge/Tools/Channels tabs, and members/invites settings.

---

## 3. NEXT: Phase 7 — Knowledge base & RAG (the heaviest phase)

Per `08-PHASES.md §7` and `06-AI-ENGINE.md §2`:
- **7.1** KB CRUD; document upload (file/url/text) → store file + `document` row + Celery enqueue.
- **7.2** Celery worker + ingestion task: parse (PDF/DOCX/TXT/CSV/MD/URL) → chunk → embed →
  store chunks/vectors → status transitions + progress. (Embeddings via Ollama `nomic-embed-text`
  or a fake embedder in tests.)
- **7.3** Retrieval: vector top-k + threshold, optional hybrid (tsvector RRF), citations.
- **7.4** Wire RAG into the chat/playground runtime: prompt assembly + citations + token budget.
- **7.5** Knowledge UI + builder Knowledge tab (wire to the new API).

This phase needs a **Celery worker** (a service already stubbed in `infra/docker-compose.yml`)
and an **embedding provider** (`EmbeddingProvider` protocol + `FakeEmbeddingProvider` already
exist in `app/llm/`). The `chunks.embedding vector(768)` column already exists.

---

## 4. How to bring the stack back up (see RUNBOOK-docker.md for detail)

```
# 1. Docker Desktop must be running, then:
cd infra && docker compose up -d postgres redis          # wait for healthy
# 2. Migrate (only if schema changed) + optionally seed:
cd ../apps/api && uv run alembic upgrade head
# 3. Run the API on the host (fast path):
uv run uvicorn app.main:app --port 8000                  # /readyz should be green
# 4. Run the web app:
cd ../web && npm run dev                                 # grabs a free port (3000/3001/…)
```
Dev CORS accepts any `http://localhost:<port>`. A demo account exists from this session:
`webflow_test@example.com` / `password123` (org "Aurozen Live", agent "Support Concierge").

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
