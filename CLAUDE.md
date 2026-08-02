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

---

## 11. Session log (append-only; newest first)

> Contract above is stable. This section is a running note of what shipped per session so a
> fresh session has context beyond git log. Full detail lives in `docs/PROGRESS.md` +
> `docs/DECISIONS.md`; keep entries here to a few lines.

### 2026-08-02 — a `.env` placeholder comment was being sent as an API key (silent live outage)
- **The live agent served empty replies with HTTP 200 to every visitor**, for an unknown period.
  Log: `...?key=%23+%5BHUMAN%5D+Google+Gemini+free+tier` — the placeholder comment *was* the key.
  `.env.example` writes unset vars as `KEY=<spaces># [HUMAN] note`; python-dotenv strips a trailing
  comment via `re.sub(r"\s+#.*", "", value)`, which needs whitespace **before** the `#`, but on a
  blank line the spaces after `=` are eaten as the separator, so `#` lands at position 0 and the
  comment becomes the value. **Probed before fixing: `KEY=dev # note` → `dev` (fine); only the
  blank-value shape breaks.** Non-empty, so it sailed past the blank-is-unset guard (ADR-020).
  `SENTRY_DSN` was failing identically; ~20 more `[HUMAN]` placeholders were one edit away.
- **Two fixes, ADR-044.** `Settings` gained a `model_validator(mode="before")` dropping
  comment-only values → **every existing `.env` is correct with no hand-editing**. `.env.example`
  reformatted (comment on its own line above each var) because `.env` also goes to containers via
  compose `env_file`, which no Python validator reaches. A test pins the file shape.
- **⚠️ Do NOT "just strip everything after the first `#`".** Measured against the real loader that
  turns `SECRET_KEY=abc#def` → `abc` and `http://x/y#frag` → `http://x/y`. Keys, DB passwords and
  URL fragments contain `#`. The narrow rule's only false positive is a secret *starting* with `#`,
  which degrades to "not configured" — loud, not silent.
- **Why it stayed invisible:** a `ProviderError` left `content` empty and `public_chat_once` only
  accumulates `token` events, so the error was dropped and the widget returned an empty 200.
  `run_turn` now takes `fallback_message` and emits it as a real token on provider failure — wired
  into `InboundTurn` (widget + channels), deliberately **not** the Playground (operators want the
  raw error). `result.error` still set; the provider message never reaches the visitor. New
  `malformed_key` startup warning for a key with whitespace or `#`.
- Suites: **349 pytest**, ruff + mypy clean.

### 2026-08-02 — replies stopped reading like a citation list; agents now start from a role
- **The research-paper voice was one clause** (`b25c1c6`): `build_context_block()`'s header told the
  model to "cite sources as [n] when relevant", so customers got "According to the documents [1]
  and [2]…". The numbering is *our* bookkeeping — the caller returns the same citations as
  structured data for the widget to render — so the header now forbids visible markers outright.
  System prompt held constant: old header **3/3** replies with `[n]`, new **0/3**, and a live call
  still returned `citations: 1`. The structured citation payload is untouched.
- **Role templates at creation time** (`a557418` backend, `a22d1ff` frontend): four prebuilt roles
  seeding the first draft's prompt/welcome/suggested prompts/tone/model, plus "Start from scratch"
  which is unchanged. Catalog is static data in `app/db/templates.py` (a fifth role is one entry —
  no schema change, no migration), served by `GET /v1/agent-templates`, applied via optional
  `template_id` on `POST /v1/agents`. Where a role needs a KB/CRM/calendar the builder shows a
  **suggestion banner, never an auto-attached tool** — a silent integration with no credentials
  behind it makes agents that look configured and fail at runtime.
- **⚠️ The tone fix caused a real accuracy regression; read this before touching a prompt**
  (`e088101`). Live, the agent invented "Mon–Fri, 9am–5pm" and a 30-day refund window against a KB
  saying Mon–Sat 10am–7pm IST / 14 days, `citations: 0` — retrieval had **legitimately missed**
  (0.0318 vs the 0.35 threshold) so **no context block was appended at all**. A/B on that exact
  state: **old prompt 0/3 fabricated, rewritten prompt 3/3.** Told only "never mention the
  documents", the model reads it as "don't hedge"; the rewrite's trailing "Just answer." made it
  explicit. The same A/B then caught a second instance in the `customer_support` template, whose
  "resolve it in as few messages" body overpowered the softer shared `_GROUNDING`. Fixed in both:
  drop "Just answer.", state the no-context case outright, scope never-narrate-your-sources to
  *phrasing*. Now **0/3** fabricated across the default prompt and all four templates, and still
  answering correctly from a real `build_context_block()` with **0/3** markers. **Never soften
  these lines without re-running the no-context A/B** — a unit test cannot see this.
- **App-wide dialog bug found on the way** (`203984a`): `animate-fade-up` ends on
  `transform: translateY(0)` with fill-mode `both`, permanently overriding `DialogContent`'s
  `-translate-*` centering — **every** dialog was anchored *at* the viewport centre, not centred on
  it. Small ones still fit, so it hid for months; the taller role picker got clipped and its
  "Start from scratch" option was unclickable. Now `inset-0 m-auto h-fit` + a scroll cap.
- Suites: **340 pytest**, ruff + mypy clean, **124 vitest**, tsc + eslint clean, **60/60 Playwright**.

### 2026-07-31 — Playground answered "echo: …"; a missing key did the same to real customers
- **Root cause was environmental, not code.** The dev web server was pointed at `:8010` — the
  keyless **E2E** API, which runs `LLM_FORCE_FAKE=true`. `get_chat_provider()` checks that flag
  *before* any per-agent config, so every agent answers with the stub echo. Proved by asking the
  same agent the same question on both ports: `:8000` → grounded Groq answer with citations,
  `:8010` → `echo: …`. The agent's stored config was never `fake` (published v1–v3 are Groq).
  Fixed by repointing the web at `:8000`; verified with a real multi-turn conversation.
- **The serious find, live in production code:** `conversations/service._resolve_provider` caught
  provider-resolution failures and substituted `FakeChatProvider()` — so an expired or revoked
  API key would answer **every visitor on a client's site** with `echo: <their own words>`. Now
  returns `RefusalProvider(fallback_message)` + logs `chat_provider_unavailable` at error level.
  The Playground re-raises the typed `llm.provider_unavailable` instead of stubbing, and
  `LLM_FORCE_FAKE=true` now announces itself loudly at startup (error-level under prod).
- **Latent bug it exposed:** `provider: "fake"` never actually resolved (`fake` isn't in
  `PROVIDER_CATALOG`, so it hit the requires-a-key branch) — it only worked because those same
  catch-alls swallowed the error. Resolved before the key check now.
- **⚠️ Needs a human:** the "aurozen ai" **draft** (v4) is `openai/gpt-4o` with no `OPENAI_API_KEY`,
  and the Playground always runs the draft — it will now say "No API key configured for 'openai'"
  rather than echo. Switch the Model tab back to Groq or add a key; published v3 is fine.
- Suites: **331 pytest**, ruff + mypy clean.

### 2026-07-31 — n8n visibility flipped to deny-by-default + staff automations console
- **The permissive default was wrong and live testing proved it.** ADR-040 kept "untagged =
  visible to every org" as a transition aid; a brand-new, empty org still saw every untagged
  workflow — other clients' automations and internal ones alike — because untagged is the state
  every workflow starts in. `workflow_visible_to_org` now grants access **only** on the org's
  slug tag or the new opt-in `shared-template`; internal tags beat both. Verified live: a fresh
  org gets `[]` where it used to get the whole list. ADR-042 supersedes ADR-040.
- **Provisioning tags at clone time**, using the org's real slug from the API (not
  `slugify(name)` — the backend suffixes on collision) and **before** the bind, since
  `/v1/tools/n8n/bind` applies the same rule and would refuse an untagged clone.
- **New staff console section** (ADR-043): `GET /v1/admin/automations` + an Automations table on
  `/admin` — every workflow across every tenant with tag-derived owner, active state and its
  bindings. Unowned rows sort first; it doubles as the tagging backlog. n8n being down returns a
  typed `error`, not a 500. Plus `scripts/tag-n8n-workflows.mjs` (dry-run by default, idempotent).
- **⚠️ The tagging itself is BLOCKED and nothing is tagged yet:** the n8n API key has workflow
  scopes but **403s on all tag endpoints**, so every workflow is currently invisible to every org.
  Bound tools keep working (the runtime uses the stored `webhook_url`), but nothing can be
  discovered or re-bound until a key with tag scopes is minted and the script re-run. `:5678` is
  a different instance entirely and 401s BotForge's key.
- Suites: **327 pytest**, ruff + mypy clean, 10 `node --test`, tsc + eslint clean.

### 2026-07-31 — logged out right after logging in (AuthGate treated an abort as a 401)
- **A navigation during session bootstrap logged the user out.** `AuthGate` runs
  `Promise.all([me(), listOrgs()])` on every page load under a bare `catch` that called
  `clearAuth()` + `/login`. Clicking a link while those are in flight **aborts** them, and an
  aborted `fetch` rejects with a `TypeError`, not a 401 — so "you navigated quickly" was read as
  "your token is invalid" and `bf_access`/`bf_org` were deleted. Traced live: both requests
  `net::ERR_ABORTED`, **zero 401s**, cookies gone. Now only `ApiError` status 401 ends a session.
- **Same fix applied to two sibling paths:** `tryRefresh()` cleared auth on any non-ok refresh
  (now 401 only), and the BFF refresh route dropped the httpOnly refresh cookie on any ≥400 —
  including a 5xx from a restarting API. It now separates a rejected token (401/400 → clear)
  from an unavailable upstream (→ 503, cookie kept), and no longer 500s when the API is down.
- **Exposed, not caused, by `fbf8543`** — wiring the dashboard to five real requests widened the
  in-flight window so an ordinary click landed inside it. PRD criterion 1 went 0/3 → 3/3 with no
  change to the test. 5 unit tests pin abort/503 ≠ sign-out.
- Suites: **320 pytest**, **116 vitest**, **54/55 Playwright** (the one failure is the known
  hardcoded-rate-limit flake — passes in isolation; see the roadmap).

### 2026-07-30 — mock data purged from the dashboard, profile and versions tab
- **Three screens rendered fixtures as real records.** `dashboard/page.tsx` imported
  `{ agents, recentConversations }` from `lib/mock/data` — a brand-new org saw four invented
  agents ("Support Concierge", "Sales Qualifier", …) and five conversations that never happened;
  `settings/profile/page.tsx` imported `currentUser`, showing **"Aadesh Sree / aadesh@aurozen.ai"
  to whoever was logged in** plus two fake devices; `versions-tab.tsx` imported `versions`,
  giving every agent the same four-entry history with dead Publish/Roll back buttons. All now
  read the API with a skeleton + a written empty state (zero-of-everything is the normal state of
  a freshly provisioned client — exactly what the fixtures hid). `lib/mock/data.ts` deleted;
  `builder.ts`'s `versions`/`makeDraft`/`knowledgeBases`/`tools` removed. See ADR-041.
- **Recent conversations reads `/v1/conversations`, not `/v1/inbox/conversations`** — the inbox
  is the *handoff queue*, so a bot resolving everything would look idle, and `viewer` lacks
  `inbox:handle` and would have hit a 403 where a fixture used to render.
- **Backend bug found on the way:** `GET /v1/auth/sessions` hardcoded `current=False`, so "This
  device" could never show. Access tokens now carry a `sid` claim; tokens without it degrade to
  the old behaviour, so rotation is unaffected. Profile name/email are **read-only** — there is
  no `PATCH /v1/auth/me`, and the old Save button silently discarded the edit (roadmap).
- **Flagged, not changed:** `providerCatalog` duplicates `GET /v1/credentials/providers` and can
  drift; switching it changes which models are selectable, so it wants its own commit (ADR-041).

### 2026-07-30 — n8n discovery scoped per org, real email delivery, one-command provisioning
1. **n8n multi-tenancy** (`6fead42`): `list_n8n_workflows` had **zero** tenant filtering — every
   org's Automations page listed every workflow in the shared n8n, platform-internal ones included
   ("SHARED — Master Router"), and could bind a tool to them. New
   `workflow_visible_to_org(tags, name, org_slug)`: tagged with an org's slug → only that org;
   tagged `internal`/`shared-internal`/`platform-internal` → hidden from everyone (fails **closed**);
   untagged → visible to all (permissive so existing untagged client workflows didn't vanish);
   `"SHARED — …"` treated as internal even untagged. Enforced at discovery **and** in
   `bind_n8n_workflow` by `workflow_id` (typed `tools.n8n_forbidden` 403), closing the
   bind-by-guessed-id hole. Binding by pasted webhook URL is deliberately **not** covered — ADR-040.
   Caught from a live screenshot, not a test: no test had two orgs' workflows in one instance.
   **The fix is inert until workflows are tagged** — audited live, 6 of 9 on the AUROZEN n8n
   (`:5678`) and all 3 on BotForge's own (`:5679`) are still untagged. See `docs/PROGRESS.md`.
2. **Email actually sends** (`898c68d`): `get_email_backend()`'s `"smtp"` branch logged
   `smtp_backend_not_implemented` and fell back to console, so no invite/verification/reset/magic-link
   had ever reached an inbox. `SmtpEmailBackend` over **aiosmtplib** + HTML templates; TLS mode from
   the port (465 implicit, else STARTTLS). Sending moved to an `email.send` Celery task — and measuring
   found `.delay()` blocks the loop and kombu retries a dead broker 20× (**30-second hung signup**), so
   the enqueue is threaded under a bounded 2s timeout and abandoned. Console mode stays **inline** (eager
   Celery would hit `asyncio.run()` inside the running loop — the §12 ingestion trap) which is what
   keeps the test outbox synchronous.
3. **One-command provisioning** (`86e0d3b`): `scripts/provision-client.mjs` → org + published agent +
   cloned/activated n8n automation bound as a tool + client invited as `editor`. Staff **login**, not a
   `bf_` key (org creation is gated on `is_staff`). Per-client webhook path — cloning the template
   verbatim would aim every client's tool at one shared URL. Two idempotency traps fixed: a pending
   invite would be re-sent (`create_invitation` only rejects *active* members), and re-patching an
   existing agent forked a draft every run **and would overwrite the client's own persona edits**.
   Dev `n8n` gained `N8N_HOST_PORT` + `N8N_DIAGNOSTICS_ENABLED=false` (it exits when
   `telemetry.n8n.io` won't resolve) and now runs on **5679**, isolated from the unrelated n8n on 5678.

Suites: **319 pytest**, **73 vitest**, **46/46 Playwright**, 8 `node --test`.

### 2026-07-29 — Edit/publish split, live widget config, invite acceptance
1. **RBAC split** (`59b8f6f`): new `AGENTS_PUBLISH` gates publish/rollback; `editor` is now the
   **client role** (edit, knowledge, own channel credentials, inbox, Playground — no publish).
   Builder shows "Awaiting review"; admin console gains an **Awaiting review** column per org.
2. **Widget config** (`60c91b2`): moved out of `AgentVersion.persona.widget` into an unversioned
   `widget_configs` table (migration `0014`). `_theme()` reads it by `agent_id`, bypassing
   `_live_version()`. New `GET/PATCH /v1/agents/{id}/widget-config` on `AGENTS_WRITE`, never
   `AGENTS_PUBLISH`. Legacy `persona.widget` writes are **routed** to the new store so old
   callers keep working instead of writing to a field nothing reads.
3. **Invite acceptance** (`0ef0b65`): the real bug — no frontend route called `accept_invitation()`.
   Page added at **`/invitations/accept`**, the path the emails already use (building at `/invite`
   would have stranded every already-sent invitation).

Suites: **297 pytest**, **73 vitest**, **46/46 Playwright**.

### 2026-07-29 — URL extraction fix, CRM rename + auto-capture
1. **URL ingest** (`49e66ba`): `strip_html()` was structure-blind, so a docs site's nav menu
   opened the extracted text and dominated the first chunk. Added **trafilatura** +
   `extract_main_content()`, `strip_html` kept as fallback. Real docs.n8n.io committed as a
   fixture; one test pins the *old* behaviour so the file records the bug.
2. **CRM rename + manual creation** (`d93b5ec`): nav/title → "CRM" (`/contacts` route kept),
   `POST /v1/contacts` with `channel="manual"` + synthetic `external_id`. `manual` added to
   `channel-meta.ts`'s `REPORTING_ONLY` so it can never become an Inbox tab.
3. **CRM auto-capture** (`a120b1f`): `CrmContact` = canonical person, `Contact` = per-channel
   handle linked via `crm_contact_id`; CRM fields moved up with a backfill (migration `0013`).
   Regex gate → one small-model call only when email/phone-shaped text exists. **Matching is by
   email/phone, never name.** Org toggle `auto_crm_capture_enabled`, on by default. Hook is in
   `_persist_user_message` (covers handoff-paused messages too).
   **Note:** the CRM now lists *people*, so a visitor who never shares an email/phone doesn't
   appear there — only in the Inbox.

Suites: **284 pytest**, **73 vitest**, **41/41 Playwright**. The E2E suite now intermittently
trips the hardcoded `public_chat`/`channel_webhook` rate limits on a full back-to-back run —
see the roadmap note in `docs/PROGRESS.md`.

### 2026-07-29 — Seven-feature batch (WhatsApp window → team performance)
Built in dependency order, one commit each:
1. **WhatsApp 24h window** (`fb6140f`) — a silent-failure bug, not a gap. `last_inbound_at`
   (separate from `last_message_at`, which our own outbound moves), `check_can_send()` hook run
   *before* persisting, typed `whatsapp_window_closed` (409), `send_template()`, Meta `131047`.
2. **Canned responses** (`39e582a`) — `/` picker in the composer (triggers only at start/after
   whitespace). Also fixed a pre-existing 500: any `field_validator` raising `ValueError`
   returned `internal_error` instead of 422.
3. **Macros** (`987feda`) — reuse the inbox service fns the manual buttons call; validate every
   step *before* applying any (a rollback can't un-send a message), then SAVEPOINT.
4. **Contacts CRM** (`37826fa`) — extends the existing `Contact`; `/contacts` page + nav.
5. **Help Center** (`61f1788`) — separate store from RAG, public pages, opt-in KB sync into a KB
   the agent *actually reads*. In-repo markdown renderer escapes before formatting.
6. **Campaigns** (`3b27bf8`) — widget triggers live; **broadcasts draft-only** (ADR-039).
7. **Team performance** (`9281d27`) — `/v1/analytics/agents`, people not channels.

Migrations `0007`–`0012`. Suites after the batch: **251 pytest**, **68 vitest**, **38 Playwright**.
**Note:** run the API *without* `CELERY_TASK_ALWAYS_EAGER` when a real worker is up — eager mode
makes the API run the async ingest task inline, where it never awaits, so ingestion never lands.

### 2026-07-29 — Inbox shows every channel tab (connected or not)
- **Reverses** the 07-28 filtering rule: `visibleChannelTabs` → `inboxChannelTabs()` (all 7, always)
  + new `isChannelConnected()`. Unconnected tabs are dimmed with a hollow dot and an `aria-label`
  of `"{Channel} (not connected)"` — status drives styling, not presence, so a user can discover
  and connect a platform from the Inbox instead of needing to know the builder exists.
- Selecting an unconnected tab replaces **both** panels with a connect prompt; the
  connected-but-quiet `"Nothing in the inbox yet."` is deliberately kept separate.
- **One credential form still**: the Inbox resolves which agent owns the channel (direct / picker /
  create-agent) and deep-links `/agents/{id}?tab=channels&connect={type}`; `MessagingChannels`
  consumes the param on mount to open the existing `ConnectDialog`, then strips it.

### 2026-07-28 — Per-channel analytics (Dashboard + Analytics breakdown)
- **Backend** (`modules/analytics/`): `Overview.by_channel` (new `ChannelBucket`), `group_by=channel`
  on `usage()`, a `channels` CSV export kind, and a `channel=` filter on every endpoint. Channel set
  = channels **with traffic ∪ channels connected & enabled** (+ always `widget`) — a plain
  `GROUP BY channel` drops a live-but-silent channel, the exact case that matters when Meta channels
  go live before any real message. Rates guard zero conversations.
- **Frontend**: one `ChannelBreakdown` component shared by Dashboard + Analytics; zero-traffic rows
  render flagged with an em dash (not `0%`). `dashboard`/`api`/`web` got real labels in
  `channel-meta.ts` as reporting-only channels (never inbox tabs).
- **Flagged, not fixed** (see `docs/PROGRESS.md` roadmap): the dashboard's `AgentsPanel` /
  `ConversationsPanel` still render `@/lib/mock/data`; the Analytics page has no date/agent filter UI
  despite the API supporting the params.

### 2026-07-28 — Unified multi-channel inbox (contacts, IG/Messenger, channel tabs)
- **Contacts** (`models/contacts.py`, migration `0006_contacts`, `app/contacts/service.py`): new
  `contacts` table unique on `(org, channel, external_id)` + `conversations.contact_id`. One upsert
  helper for every inbound path (channels **and** the widget's `Visitor`); `COALESCE(new, old)` +
  JSONB merge so a nameless payload never erases a known name. New `BaseChannel.fetch_profile` hook,
  called only while a contact still lacks a name/avatar.
- **Instagram + Facebook Messenger**: `channels/instagram.py` + `facebook.py` over a shared
  `meta_messaging.py`; Meta's signature/challenge logic factored out of `whatsapp.py` into
  `meta_signature.py` (all three Meta surfaces now share one verification path). Deliveries matched
  on webhook `object`; echoes/read receipts ignored. **Comment moderation deliberately excluded** — ADR-037.
- **Inbox**: nested `contact` on list/detail (batched), `?channel=` filter, and a channel tab bar
  (Web Chat always; others only once an enabled `Channel` row exists — **superseded 2026-07-29**,
  all tabs now always render) with contact avatars +
  platform badges. ADR-036 (no Telegram avatar — its photo URLs embed the bot token), ADR-038.

### 2026-07-27 — Widget preview single-host + app sidebar
- **Widget preview overlap** (`packages/widget/src/widget.js`): live Playwright diagnosis in the
  real Channels tab confirmed a **single** `#botforge-widget` host (not a duplicate mount). The
  white/black "overlap" was an unstyled first-paint frame. Fixed `build()`: remove any pre-existing
  host (idempotency) + build **detached** and theme via `applyConfig()` *before* `appendChild` — no
  unstyled frame. Playwright asserts one host across config posts + open/close.
- **App sidebar** (`apps/web/src/components/shell/sidebar*.tsx`): footer (Scale plan + Collapse) was
  pushed below the fold — the `<nav>` lacked `min-h-0` and the `aside` was `lg:static` under a
  `min-h-screen` shell (unbounded). Fixed with `min-h-0` on the nav + `lg:sticky lg:top-0 lg:h-screen`
  on the aside; added a **header collapse toggle** next to the logo (both states) sharing
  `toggleCollapsed`. Commits `73a949c`, `f1db62e`.

### 2026-07-21 — Widget customization parity + fixes
- Full widget customization (styles/colors/fonts/logo/launcher designs/live preview) — ADR-035.
- Fixes: preview no longer force-opens on config change (`build`/`applyConfig` split); transparent
  glass palette; real launcher SVGs in the picker; mobile launcher-vs-panel collision hidden
  `<768px` via a `bf-open` host class. RAG fix: support-bot default prompt + `score_threshold` 0.7→0.35.

### 2026-07-19/20 — Phases 19–20 complete; repo published
- Phase 19 (E2E for PRD criteria 1–7, Next 14→16 upgrade, docs, a11y) + Phase 20 (prod compose +
  Caddy TLS, Redis pub/sub hub, webhook retry sweep, httpOnly refresh via BFF, /metrics + Sentry +
  backups, K8s manifests, release CI/CD). Phase 18 (billing) deferred by design. Tagged
  `phase-19-complete`, `phase-20-complete`. Pushed to `github.com/aadesh2025/botforge` (private).

## 12. Dev-stack reality (Windows, this machine)

Each new session usually starts with Docker Desktop + services **stopped** — bring them up first:
1. **Docker Desktop** must be running, then `cd infra && docker compose up -d postgres redis` (wait healthy).
2. **API** (from `apps/api`): `./.venv/Scripts/python.exe -m uvicorn app.main:app --port 8000`
   (+ a Celery worker `--pool=solo` for ingestion). For keyless E2E, add `LLM_FORCE_FAKE=true` and
   run on port **8010** (see below).
3. **Web** (from `apps/web`): `npm run dev -- -p 3001`. Open **http://localhost:3001**.

**Port gotchas:** canonical is web **3000** / API **8000**, but on this machine **3000 is taken by
an unrelated app**, so BotForge web runs on **3001**. The keyless-E2E API runs on **8010**
(`LLM_FORCE_FAKE=true`, `AUTH_RATE_LIMIT` lifted) so it doesn't clash with a real :8000 API.
**n8n** is expected at **5678** (`N8N_BASE_URL`) — note the running `:5678` belongs to the separate
AUROZEN AI compose, not BotForge's own `n8n` service. Always run API/web commands from `apps/api` /
`apps/web` (not the repo root) to avoid `ModuleNotFoundError: app` / npm ENOENT.
