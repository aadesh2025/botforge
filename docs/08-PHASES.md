# 08 — Build Plan (Phases & Tasks) — EXECUTE IN ORDER, NO STOPPING

> **Autonomous rule (from `CLAUDE.md §1`):** Execute every phase from Phase 0 to Phase 20 in
> order, task by task. **Do not pause for approval between tasks or phases.** After each
> task: ensure it meets the Definition of Done (`CLAUDE.md §2`), commit, and continue to the
> next task automatically. Only stop for a human-only secret (`CLAUDE.md §7`) — and even
> then, stub it, log a loud warning, and keep building.
>
> Each task lists: **Do**, and **Done when** (its acceptance check). Update
> `docs/PROGRESS.md` after each phase and `git tag phase-NN-complete`.

Legend: `[api]` backend, `[web]` frontend, `[infra]`, `[widget]`, `[test]`, `[docs]`.

---

## PHASE 0 — Repo, tooling, CI, compose skeleton
- **0.1** `[infra]` Create the repo layout from `CLAUDE.md §5`. Init git, `.gitignore`,
  `.editorconfig`, LICENSE, root `README.md`. **Done when** repo tree exists and initial
  commit is made.
- **0.2** `[api]` Scaffold FastAPI app: `apps/api` with `pyproject.toml` (FastAPI, uvicorn,
  SQLAlchemy, asyncpg, alembic, pydantic-settings, redis, celery, argon2-cffi, httpx,
  python-jose, ruff, mypy, pytest). Add `main.py` with `/healthz`, `/readyz`, `/version`,
  settings via Pydantic. **Done when** `uvicorn` serves `/healthz` returning 200 and
  `ruff`+`mypy` pass.
- **0.3** `[web]` Scaffold Next.js 14 app in `apps/web` (TS strict, Tailwind, shadcn/ui init,
  eslint, prettier, vitest). Landing page placeholder. **Done when** `next build` succeeds
  and `/` renders.
- **0.4** `[infra]` `infra/docker-compose.yml` with services: `postgres` (pgvector image),
  `redis`, `api`, `web`, `n8n`, `ollama`. Healthchecks, volumes, `.env` wiring. **Done when**
  `docker compose up` starts all services and api `/readyz` is green (DB+Redis reachable).
- **0.5** `[infra]` `.env.example` + `docs/ENV.md` with every planned var (LLM keys, OAuth,
  channels, `SECRET_KEY`, DB/REDIS URLs, `N8N_BASE_URL`, `N8N_API_KEY`, `OLLAMA_BASE_URL`).
  **Done when** files list all vars from `CLAUDE.md §7` with comments.
- **0.6** `[infra]` GitHub Actions CI: lint+typecheck+test for api and web on push/PR.
  **Done when** workflow file exists and passes locally (`act` or manual run of the steps).
- **0.7** `[api]` `Makefile`/`justfile` with `dev, test, lint, fmt, migrate, seed, up, down`.
  **Done when** `make lint` and `make test` run (empty suites ok).
- **Gate:** `docker compose up` yields healthy stack; CI config committed; tag `phase-00-complete`.

## PHASE 1 — Database foundation & migrations
- **1.1** `[api]` Async SQLAlchemy engine/session, base model (UUIDv7 pk, timestamps,
  soft-delete mixin), Alembic configured for async. **Done when** `alembic upgrade head` runs
  on an empty DB.
- **1.2** `[api]` Enable `vector` + `pgcrypto` extensions via migration. **Done when**
  extensions present after migrate.
- **1.3** `[api]` Implement identity/tenancy tables (`users, oauth_accounts,
  magic_link_tokens, password_reset_tokens, sessions, organizations, memberships,
  invitations`) per `03`. **Done when** migration applies and models import cleanly.
- **1.4** `[api]` Implement remaining tables (agents, agent_versions, provider_credentials,
  knowledge_bases, documents, chunks[+vector], conversations, messages, tools, tool_runs,
  channels, handoffs, api_keys, webhook_endpoints, webhook_deliveries, audit_logs,
  usage_records, quotas, subscriptions). **Done when** full migration applies with all
  indexes from `03 §Indexing`.
- **1.5** `[api]` Repository base class enforcing `organization_id` scoping; pagination
  helper. **Done when** unit test proves cross-org queries return nothing.
- **1.6** `[api]` Seed script (`make seed`) creating demo org/user/agent/KB/tool/channel per
  `03 §Seed`. **Done when** seed runs and rows exist.
- **Gate:** migrations + seed reproducible from scratch; tag `phase-01-complete`.

## PHASE 2 — Auth & accounts
- **2.1** `[api]` Password auth: argon2 hashing, signup/login, JWT access+refresh, refresh
  rotation, logout, `/auth/me`. **Done when** integration tests cover signup→login→refresh→
  logout.
- **2.2** `[api]` Email verification + password reset (token tables, email sender interface
  with console/dev backend). **Done when** flows tested with the fake email backend.
- **2.3** `[api]` Magic-link login. **Done when** tested end-to-end with fake email.
- **2.4** `[api]` OAuth (Google, GitHub) with PKCE/state; link to `oauth_accounts`. **Done
  when** callback creates/links a user (mock provider in tests; real keys stubbed per §7).
- **2.5** `[api]` Sessions list/revoke; rate limiting on auth endpoints. **Done when** tested.
- **2.6** `[web]` Auth pages (login/signup/forgot/reset/verify/magic), cookie handling,
  middleware guarding `/app/*`, refresh proxy route. **Done when** Playwright can sign up and
  reach `/dashboard`.
- **Gate:** full auth journey works in the browser; tag `phase-02-complete`.

## PHASE 3 — Organizations, membership, RBAC
- **3.1** `[api]` Org CRUD, current-org resolution (`X-Org-Id` + membership check dependency).
  **Done when** a user can create/list/switch orgs; non-members get 403.
- **3.2** `[api]` Memberships + invitations (invite/accept/role change/remove/transfer).
  **Done when** invite→accept flow tested with fake email.
- **3.3** `[api]` RBAC dependency/decorator implementing the `02 §6` matrix; audit-log writes
  on sensitive mutations. **Done when** permission tests pass for each role.
- **3.4** `[web]` Org switcher in shell, `settings/org` (members, invitations, roles),
  RoleGuard component. **Done when** UI reflects roles and hides forbidden actions.
- **Gate:** multi-tenant isolation + roles verified by tests; tag `phase-03-complete`.

## PHASE 4 — App shell & design system
- **4.1** `[web]` Build the design tokens + dark mode + core shadcn/ui component wrappers
  (`05 §8`). **Done when** a component gallery/storybook-lite page renders all states.
- **4.2** `[web]` App shell: sidebar, top bar, org switcher, user menu, theme toggle,
  responsive. **Done when** navigation renders and links resolve.
- **4.3** `[web]` Typed API client generated from `openapi.json`; TanStack Query provider;
  toast + error boundary. **Done when** a real authenticated call (e.g., `/auth/me`) renders
  in the dashboard.
- **Gate:** shell + design system usable; tag `phase-04-complete`.

## PHASE 5 — LLM provider layer (Groq-first)
- **5.1** `[api]` `llm/` interfaces (`ChatProvider`, `EmbeddingProvider`, request/response,
  stream events) + `FakeProvider`/`FakeEmbeddingProvider`. **Done when** fakes stream in tests.
- **5.2** `[api]` `OpenAICompatibleProvider` + Groq/OpenRouter/Ollama/custom subclasses;
  model discovery. **Done when** Groq chat + stream works against a live key **or** is fully
  exercised via a mocked HTTP layer when the key is absent.
- **5.3** `[api]` Gemini adapter + Anthropic adapter + OpenAI (same base). **Done when**
  message/tool translation unit-tested per provider.
- **5.4** `[api]` Provider resolution (agent→org→env keys), encryption of stored keys,
  fallback chain, usage/cost accounting + `PRICING`. **Done when** fallback + cost tests pass.
- **5.5** `[api]` `/v1/credentials` endpoints (CRUD, test, list providers/models). **Done
  when** keys can be added (masked) and `test` validates against a provider (mock if no key).
- **Gate:** an agent config can produce a streamed completion via fakes/mocks and real Groq
  when keyed; tag `phase-05-complete`.

## PHASE 6 — Agents & versions (builder backend)
- **6.1** `[api]` Agent CRUD + duplicate + public_key generation. **Done when** tested.
- **6.2** `[api]` Agent versions: create draft, patch persona/model_config/rag_config/
  features/prompts, publish, rollback, current_version pointer. **Done when** version
  lifecycle tested.
- **6.3** `[api]` Playground chat endpoint using the draft version + LLM layer (no RAG yet).
  **Done when** streaming playground responds in tests.
- **6.4** `[web]` Agents list + create; agent builder Persona & Model tabs wired to the API
  with autosave; Playground panel streaming. **Done when** a user configures Groq + persona
  and chats in the playground.
- **Gate:** create→configure→playground→publish works in the browser; tag `phase-06-complete`.

## PHASE 7 — Knowledge base & RAG
- **7.1** `[api]` KB CRUD; document upload (file/url/text) storing file + `document` row +
  Celery enqueue. **Done when** upload creates a queued document.
- **7.2** `[api]` Celery worker + ingestion task: parse (PDF/DOCX/TXT/CSV/MD/URL) → chunk →
  embed → store chunks/vectors → status transitions + progress. **Done when** a sample PDF
  reaches `ready` with chunks (embeddings via Ollama/fake in tests).
- **7.3** `[api]` Retrieval: vector top-k + threshold, optional hybrid (tsvector RRF),
  citations. **Done when** `/knowledge/{id}/search` returns ranked chunks + scores.
- **7.4** `[api]` Wire RAG into chat runtime: prompt assembly with retrieved context +
  citations + token budgeting. **Done when** an agent answers from an uploaded doc and
  returns citations in the stream.
- **7.5** `[web]` Knowledge UI (upload/dropzone, status badges, progress, chunk viewer,
  retrieval test) + builder Knowledge tab. **Done when** upload→ready→cited answer works in UI.
- **Gate:** grounded, cited answers from user docs; tag `phase-07-complete`.

## PHASE 8 — Chat persistence, memory, conversations
- **8.1** `[api]` Persist conversations/messages with usage/cost/latency; conversation list +
  detail + messages endpoints. **Done when** history is stored and browsable.
- **8.2** `[api]` Memory: short-term window + long-term summarization into `memory_summary`
  (cheap free model). **Done when** long conversations stay within budget (tested).
- **8.3** `[api]` WebSocket chat endpoint (dashboard) mirroring SSE contract. **Done when** WS
  streams tokens.
- **8.4** `[web]` Conversations browser + wire playground/chat to persisted history. **Done
  when** past conversations render with citations/tool markers.
- **Gate:** durable chat with memory; tag `phase-08-complete`.

## PHASE 9 — Tools & tool calling
- **9.1** `[api]` Built-in tools (`knowledge_search`, `get_datetime`, `calculator`,
  guarded `http_request`, `web_search` stub) with JSON schemas. **Done when** unit-tested.
- **9.2** `[api]` Tool-calling loop in chat runtime (execute → feed back → continue, with
  iteration cap) + `tool_runs` logging. **Done when** an agent calls a tool and uses its
  result (tested with a fake tool + FakeProvider that requests it).
- **9.3** `[api]` HTTP tool builder + execution (SSRF guards, templating, timeouts). **Done
  when** a user-defined HTTP tool executes and logs a run.
- **9.4** `[web]` Builder Tools tab: toggle built-ins, create/test HTTP tools, view runs.
  **Done when** create→test→use in playground works.
- **Gate:** agent uses tools mid-conversation; tag `phase-09-complete`.

## PHASE 10 — n8n integration
- **10.1** `[infra]` Ensure n8n in compose; `integrations/n8n_client` (list workflows, trigger
  webhook signed, verify callback). **Done when** client lists workflows from local n8n (or
  mocked) and triggers a webhook.
- **10.2** `[api]` n8n tool type: bind workflow → callable tool; sync + async modes + callback
  endpoint. **Done when** agent triggers an n8n workflow and receives its result (sync) and an
  async callback resolves a pending run.
- **10.3** `[infra]` Ship starter workflows in `infra/n8n/` + import docs. **Done when** JSON
  exports exist and are documented.
- **10.4** `[web]` `/automations` page: list n8n workflows, bind as tools. **Done when** UI
  binds a workflow and it appears in the agent's Tools tab.
- **Gate:** end-to-end agent→n8n automation works; tag `phase-10-complete`.

## PHASE 11 — Embeddable web widget
- **11.1** `[api]` Public config + public chat (SSE + WS) endpoints keyed by `public_key`,
  rate-limited, visitor identity optional. **Done when** public chat streams without dashboard
  auth.
- **11.2** `[widget]` Build the widget (Shadow DOM, launcher, streaming chat, markdown,
  quick replies, file upload, theming) → single `widget.js`+`widget.css`; JS SDK API. **Done
  when** an example static HTML page embeds and chats.
- **11.3** `[web]` Builder Channels tab: widget theme/colors/position/branding + live preview
  + copyable embed snippet. **Done when** snippet copied from UI works on a test page.
- **Gate:** widget embed on a plain HTML page chats with the agent; tag `phase-11-complete`.

## PHASE 12 — Messaging channels
- **12.1** `[api]` Channel abstraction (`verify/parse_inbound/send`) + registry. **Done when**
  interface + tests exist.
- **12.2** `[api]` Telegram channel (webhook set, inbound parse, send). **Done when** a
  Telegram message round-trips (mock Telegram API in tests; real token stubbed per §7).
- **12.3** `[api]` WhatsApp (Meta) channel incl. verify challenge + signature. **Done when**
  round-trip tested with mocks.
- **12.4** `[api]` Slack + Discord channels (signature verify, events, send). **Done when**
  tested with mocks.
- **12.5** `[web]` Channels tab connect flows for each channel. **Done when** a channel can be
  configured and enabled from the UI.
- **Gate:** at least Telegram works end-to-end with a real token if provided; tag
  `phase-12-complete`.

## PHASE 13 — Inbox & human handoff
- **13.1** `[api]` Handoff trigger (tool/keyword/intent) pausing the bot; `handoffs` records;
  inbox endpoints (takeover/handback/reply/assign/close/notes/tags). **Done when** handoff
  lifecycle tested.
- **13.2** `[api]` Real-time inbox updates over WS. **Done when** operator replies stream to
  the end user and updates appear live.
- **13.3** `[web]` Inbox UI (list + thread, takeover, reply, assign, notes, tags, handback).
  **Done when** an operator handles a handed-off conversation across channels.
- **Gate:** bot→human→bot handoff works live; tag `phase-13-complete`.

## PHASE 14 — Analytics & usage metering
- **14.1** `[api]` Usage rollups (Celery) into `usage_records`; quotas + threshold events.
  **Done when** token/cost usage aggregates correctly (tested).
- **14.2** `[api]` Analytics endpoints (overview, usage, latency, top/unanswered, CSV export).
  **Done when** endpoints return correct aggregates on seeded data.
- **14.3** `[web]` Analytics dashboards (cards + Recharts + date range + export). **Done when**
  charts render real metrics.
- **Gate:** analytics reflect real activity; tag `phase-14-complete`.

## PHASE 15 — API keys, outbound webhooks, audit
- **15.1** `[api]` API key issuance (`bf_` prefix, hashed, scopes, last-used) + auth accepting
  API keys. **Done when** an API key can call the public/programmatic API.
- **15.2** `[api]` Outbound webhooks: endpoints CRUD, signed delivery with retries, delivery
  log, event catalog emission across the app. **Done when** events deliver and retry (tested).
- **15.3** `[api]` Audit log endpoints + ensure sensitive mutations are recorded. **Done
  when** audit entries appear for role changes, key creation, etc.
- **15.4** `[web]` Settings pages: API keys, webhooks, (audit log viewer). **Done when**
  manageable from UI.
- **Gate:** programmatic access + webhooks operational; tag `phase-15-complete`.

## PHASE 16 — Guardrails, moderation, hardening
- **16.1** `[api]` Guardrails (blocked topics, prompt-injection heuristics on untrusted
  content, output redaction hook). **Done when** guardrail tests pass.
- **16.2** `[api]` Security pass: rate limits everywhere public, SSRF guards, CSP/security
  headers, encrypted-key audit, input/file validation review. **Done when** a security
  checklist in `docs/SECURITY.md` is satisfied and tests cover the guards.
- **16.3** `[test]` Load/perf sanity (locust/k6 script) checking NFR-1 targets on Groq.
  **Done when** a perf script exists and p50 first-token target is measured/recorded.
- **Gate:** security checklist green; tag `phase-16-complete`.

## PHASE 17 — Admin console
- **17.1** `[api]` `is_staff` admin endpoints (orgs, users, usage, health, feature flags).
  **Done when** staff-only access enforced + tested.
- **17.2** `[web]` `/admin` console UI. **Done when** staff can view platform data.
- **Gate:** admin console works, non-staff blocked; tag `phase-17-complete`.

## PHASE 18 — Billing (OPTIONAL / stretch)
- **18.1** `[api]` Stripe: customer/subscription, checkout, portal, webhook → plan/quota sync.
  **Done when** checkout→webhook→plan update works in Stripe test mode (stub if no keys).
- **18.2** `[web]` `settings/billing`. **Done when** plan + usage shown.
- **Gate:** billing optional-complete or explicitly deferred in `PROGRESS.md`;
  tag `phase-18-complete`.

## PHASE 19 — Full E2E, docs, polish
- **19.1** `[test]` Playwright E2E covering PRD acceptance criteria 1–7 (`01 §6`). **Done
  when** all E2E specs pass in CI against the compose stack.
- **19.2** `[docs]` User/admin README, self-host guide, API usage guide, widget install guide,
  n8n setup guide. **Done when** docs exist and are accurate.
- **19.3** `[web]` UX polish: empty/loading/error states everywhere, a11y audit, mobile pass.
  **Done when** a11y + responsive checks pass.
- **Gate:** all MVP acceptance criteria pass; tag `phase-19-complete`.

## PHASE 20 — Production deployment
- **20.1** `[infra]` `docker-compose.prod.yml` + reverse proxy (Caddy/Nginx) + TLS + env
  hardening + non-root images + healthchecks. **Done when** prod compose boots the full stack.
- **20.2** `[infra]` Backups (pg_dump cron), log aggregation, `/metrics` + basic alerts,
  Sentry hook. **Done when** backup + metrics documented and working.
- **20.3** `[infra]` (Stretch) Kubernetes manifests/Helm. **Done when** manifests exist or
  explicitly deferred.
- **20.4** `[infra]` CI/CD: build+push images, deploy step, run migrations on deploy. **Done
  when** pipeline builds and (dry-run) deploys.
- **Gate:** production-ready deploy path documented and demonstrated; tag `phase-20-complete`.

---

## Execution reminders
- **Never stop between tasks for approval.** Keep the loop: implement → satisfy Definition of
  Done → commit → next task.
- If a real credential is missing, stub the provider/channel, log a loud warning, note it in
  `docs/ENV.md` under "needs human", and continue.
- Keep `docs/PROGRESS.md` (shipped + roadmap) and `docs/DECISIONS.md` (ADRs) current.
- Run `make test` + Playwright smoke at each phase gate before tagging.
