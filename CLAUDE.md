# CLAUDE.md — Build Rules & Operating Contract

> This file is the **operating contract** for Claude Code building this project.
> Read this file first, then read `docs/00-README.md`, then start Phase 0 in
> `docs/08-PHASES.md`. Follow the phases **in order, task by task**.

---

## 0. Project one-liner

Build **"BotForge"** — an original, enterprise-grade, Botpress-inspired AI chatbot &
automation platform. Multi-tenant SaaS: users create AI agents (chatbots), give them a
persona/temperature/model, attach a knowledge base (RAG), embed a chat widget, connect
channels (WhatsApp/Telegram/etc.), and wire automations to a **locally-running n8n**
instance over connectors. This is an **original implementation** — inspired by Botpress'
public feature set, NOT a copy of its code, UI, or backend.

## 1. Autonomous execution — DO NOT STOP FOR APPROVAL

- Work through `docs/08-PHASES.md` **from Phase 0 to the final phase without pausing for
  approval between tasks or phases.** Do not ask "should I continue?" — continue.
- Only stop and ask the human when you hit a **hard blocker** that you genuinely cannot
  resolve yourself: a missing secret/credential that only the human can create (see §7),
  or a destructive action against real user data. Everything else: decide and proceed.
- After finishing each task, mark it done in your own TODO tracking, commit, and move to
  the next task automatically.
- If something is ambiguous, pick the **most standard, production-grade** option, write
  down the decision in `docs/DECISIONS.md`, and keep going.
- Never leave the build in a broken state at the end of a task. Every task ends with code
  that compiles/typechecks and with its tests passing.

## 2. Definition of Done (applies to EVERY task)

A task is done only when ALL are true:
1. Code compiles / typechecks with **zero errors** (`tsc --noEmit`, `ruff`, `mypy` clean).
2. Lint passes (`eslint`, `ruff`) with zero errors.
3. New logic has tests, and **the full test suite passes** (`pytest`, `vitest`).
4. If it touches UI, a Playwright check exists and passes (see `docs/10-TESTING.md`).
5. It is committed to git with a Conventional Commit message.
6. Any new env var is added to `.env.example` with a comment and to `docs/ENV.md`.

## 3. Git workflow

- Initialize git at Phase 0. Commit after **every task**, not every phase.
- Conventional Commits: `feat:`, `fix:`, `chore:`, `docs:`, `test:`, `refactor:`.
- One branch per phase is fine (`phase/03-ai-engine`) but committing to `main` directly
  is acceptable for a solo build. Never force-push.
- Tag the end of each phase: `git tag phase-03-complete`.

## 4. Tech stack (FIXED — do not substitute)

| Layer | Choice |
|---|---|
| Frontend | **Next.js 14** (App Router, TypeScript), Tailwind CSS, shadcn/ui, Framer Motion, TanStack Query, Zustand |
| Backend | **Python 3.11 + FastAPI**, Pydantic v2, SQLAlchemy 2.0 (async), Alembic |
| DB | **PostgreSQL 16** + **pgvector** extension |
| Cache/Queue | **Redis 7** (cache, rate limits, Celery broker), **Celery** for background jobs |
| Vector store | pgvector (default). Abstract behind an interface so Qdrant can be swapped in later |
| Auth | JWT access + refresh, OAuth (Google/GitHub), password (argon2), magic links |
| LLM | **Groq first**, then other free (OpenRouter free tier, Google Gemini free, Ollama local), then **OpenAI** and **Anthropic** paid |
| Embeddings | Free-first: `nomic-embed-text` via Ollama or Groq/OpenAI-compatible; fallback OpenAI `text-embedding-3-small` |
| Automation | **n8n** running in Docker locally (see §6), connected via REST + webhooks |
| Realtime | WebSockets (FastAPI) + SSE for token streaming |
| Deploy | Docker Compose (dev + prod), Nginx/Caddy reverse proxy, Kubernetes manifests as stretch |
| Tests | pytest + httpx (backend), Vitest + Testing Library (frontend unit), **Playwright** (E2E) |
| CI | GitHub Actions |

Do not introduce a different framework without recording the reason in `docs/DECISIONS.md`.

## 5. Repository layout (create at Phase 0)

```
own_chatbot/
├─ CLAUDE.md                 # this file
├─ docs/                     # the spec (source of truth)
├─ apps/
│  ├─ web/                   # Next.js frontend
│  └─ api/                   # FastAPI backend
├─ packages/
│  └─ widget/                # embeddable chat widget SDK (vanilla TS, builds to 1 JS file)
├─ infra/
│  ├─ docker-compose.yml     # dev: postgres, redis, api, web, n8n, ollama
│  ├─ docker-compose.prod.yml
│  ├─ nginx/ | caddy/
│  └─ k8s/                   # stretch
├─ .github/workflows/
├─ .env.example
└─ README.md
```

## 6. n8n integration rule

- n8n runs in Docker on the local machine (assume `http://localhost:5678`, configurable via
  `N8N_BASE_URL`). Add an `n8n` service to the dev compose file so the whole stack comes up
  together, but also support pointing at an already-running n8n instance.
- Integrate two ways: (a) BotForge **calls** n8n workflows via webhook/REST to run
  automations; (b) n8n **calls** BotForge via signed webhooks/REST API + API keys.
- Never hardcode the n8n URL or key — read from env. See `docs/07-INTEGRATIONS.md`.

## 7. Secrets Claude cannot invent (STOP and ask the human ONLY for these)

Put every one of these in `.env.example` with a placeholder and instructions. If a phase
needs one that isn't set, implement the code + a clear runtime error/log telling the human
what to add, then **continue** with a mock/stub so the build isn't blocked:

- LLM keys: `GROQ_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `OPENROUTER_API_KEY`
- OAuth: `GOOGLE_CLIENT_ID/SECRET`, `GITHUB_CLIENT_ID/SECRET`
- Channels: WhatsApp/Meta `META_APP_SECRET` + tokens, `TELEGRAM_BOT_TOKEN`, Twilio, Slack, Discord
- Billing (stretch): `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`
- Infra: `SECRET_KEY` (JWT), `N8N_API_KEY`

**Rule:** never block the whole build waiting on a key. Stub the provider, log a loud
warning, keep building. Real keys get dropped in later by the human.

## 8. Coding standards

- **Backend:** async everywhere, typed, Pydantic schemas for every request/response,
  service layer separated from routers, repository pattern for DB access, no business
  logic in routers. Alembic migration for every schema change. Structured logging (JSON).
- **Frontend:** server components by default, client components only when needed, all API
  calls through a typed client generated from the OpenAPI spec, no `any`, colocate tests.
- **Security:** validate all input, parametrized queries only, tenant isolation enforced at
  the query layer (every query filtered by `organization_id`), rate-limit public endpoints,
  encrypt provider API keys at rest, never log secrets. Follow `docs/02-ARCHITECTURE.md §Security`.
- **Errors:** typed error responses `{error: {code, message, details}}`, never leak stack
  traces to clients in prod.

## 9. When you finish a phase

Run the full suite (`make test`), run the Playwright smoke, update `docs/PROGRESS.md`
with what shipped, tag git, and **immediately start the next phase**. Do not wait.

## 10. Reading order

1. `CLAUDE.md` (this file)
2. `docs/00-README.md`
3. `docs/01-PRD.md`
4. `docs/02-ARCHITECTURE.md`
5. `docs/03-DATABASE-SCHEMA.md`
6. `docs/04-API-SPEC.md`
7. `docs/05-FRONTEND.md`
8. `docs/06-AI-ENGINE.md`
9. `docs/07-INTEGRATIONS.md`
10. `docs/09-DEPLOYMENT.md`
11. `docs/10-TESTING.md`
12. `docs/08-PHASES.md` ← then execute this, task by task, no stopping.
