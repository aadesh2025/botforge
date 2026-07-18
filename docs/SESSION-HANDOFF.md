# SESSION HANDOFF — BotForge

> **Read this first, then continue the build.** This file is the pick-up point for the next
> session. It records what's done, what's half-done, and exactly what to do next.

Last updated: **2026-07-18** · Latest commit: `ef508a7` · Branch: `master`

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

**Continue from where we left off: Phase 8 (Chat persistence, memory, conversations).**

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
| 8 | **Chat persistence & memory** | ⬜ **NOT STARTED — do this next** |
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

**Scoreboard:** 7 phases tagged complete (0,1,2,4,5,6,7) · 1 mostly done (3) · 13 not started (8–20).
Roughly **7 of 21** phases have real, tested, wired progress.

### Backend business routes live now
`/v1/auth/*`, `/v1/orgs/*`, `/v1/credentials/*`, `/v1/agents/*` (+ playground), `/v1/knowledge/*`
(KB CRUD, document upload file/url/text, chunks, `/{id}/search`). Everything else in
`04-API-SPEC.md` is not built yet.

### Frontend: what's real vs mock
- **Real (wired to API):** login/signup, org switcher, user menu, agents list + builder
  (Persona/Model/Versions/**Knowledge** + playground), credentials settings, **knowledge
  list + detail (upload/url/text, live status, chunk viewer)**.
- **Still mock (no backend yet):** dashboard analytics, inbox, analytics, automations, the
  builder's Tools/Channels tabs, and members/invites settings.

---

## 3. NEXT: Phase 8 — Chat persistence, memory, conversations

Per `08-PHASES.md §8` and `06-AI-ENGINE.md §3`:
- **8.1** Persist conversations/messages (usage/cost/latency); conversation list + detail +
  messages endpoints. Currently the playground is stateless — nothing is written to
  `conversations`/`messages`.
- **8.2** Memory: short-term window + long-term summarization into `memory_summary` (cheap
  free model) when history exceeds a threshold.
- **8.3** WebSocket chat endpoint mirroring the SSE contract.
- **8.4** Conversations browser (web) + wire the playground/chat to persisted history.

The `conversations` + `messages` models already exist (Phase 1). The RAG runtime in
`app/modules/agents/service.py` (`_retrieve_context`, `_build_request`, `playground_stream/once`)
is where message persistence + memory assembly should hook in.

### Phase 7 leftovers / gotchas discovered
- **Builder autosave 409 on published agents:** the builder edits the *latest* version, but for
  a **published** agent that version is immutable (PATCH → 409) so edits silently don't persist.
  The builder should create a new draft version when the latest is published (a Phase 6/8 UX
  fix). Test RAG in the playground on a **draft** agent.
- **RAG UI works end-to-end on a draft agent** — proven live by pointing the "aadesh" draft
  agent at Ollama `qwen3:14b` with the "Product Docs" KB (id `019f7164-…`) attached.
- Hybrid FTS uses `plainto_tsquery` which **ANDs** all query tokens; a query only matches
  lexically when every non-stopword token appears in a chunk (see ADR-021).

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
