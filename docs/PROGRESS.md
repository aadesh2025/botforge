# PROGRESS.md — Build Progress & Roadmap

Claude Code updates this after every phase (per `CLAUDE.md §9`): what shipped, what's
stubbed/deferred, and any gaps waiting on human secrets.

## Status by phase
| Phase | Title | Status | Notes |
|---|---|---|---|
| 0 | Repo/tooling/CI/compose | ✅ | git, web + api scaffolds, docker-compose (postgres+pgvector/redis/api/worker/web/n8n/ollama), .env.example, Makefile, CI. **Verified: `docker compose up postgres redis` healthy, `/readyz` green (db+redis reachable).** Remaining: on-start alembic in api container (later), Playwright in CI (Phase 19). |
| 1 | Database foundation | ✅ | All 27 models, UUIDv7 base + mixins, org-scoped repository (cross-org isolation test), Alembic async. **Verified against real Postgres: `alembic upgrade head` created all 27 tables + pgcrypto/vector extensions + `chunks.embedding vector(768)`; seed ran (idempotent); 10 tests + ruff + mypy green.** |
| 2 | Auth & accounts | ✅ | Backend (argon2/JWT+rotating refresh/verify/reset/magic-link/OAuth/sessions/rate-limit). **2.6 web auth done: login+signup pages + cookie token store + route-guard middleware + AuthGate (/me+orgs bootstrap, create-first-org). Verified live: signup→org→dashboard, login→dashboard.** Tagged phase-02-complete. |
| 3 | Orgs/RBAC | ✅ | Backend complete (CRUD/members/invites/transfer/RBAC/audit). **3.4 gap closed in Phase 15: org members + invitations settings UI wired to `/v1/orgs/*`, and a real `lib/rbac` matrix / `useCan` gate (mirrors docs/02 §6). Verified live: a viewer-role member gets 403 on admin actions and a read-only UI.** |
| 4 | App shell & design system | ✅ | Design tokens, dark-first ember system, full app shell + dashboard. **4.3 done: typed API client (`lib/api`, hand-written) with Bearer+X-Org-Id+401-refresh + SSE reader; real `/me` renders in shell.** Tagged phase-04-complete. |
| 5 | LLM provider layer | ✅ | app/llm: ChatProvider/EmbeddingProvider protocols, Fake providers, OpenAICompatible base + Groq/Ollama/OpenRouter/OpenAI/custom (chat+stream+models), Gemini + Anthropic adapters (native translation), PRICING + cost, provider resolution (agent→org→env) w/ Fernet-decrypted keys, fallback chain. /v1/credentials CRUD (masked) + test + /providers catalog. 54 tests pass (mock HTTP transport, no live keys needed); ruff+mypy clean. Tagged phase-05-complete. |
| 6 | Agents & versions | ✅ | Backend (CRUD/duplicate/versions/publish/rollback/playground stream). **6.4 done: agents list + builder wired to real API — loads real agent+version, debounced autosave (PATCH), publish, and real SSE playground streaming. Verified live: create→configure→autosave persists→publish→playground streams (echo fallback + graceful provider-error surfacing).** 61 tests pass; ruff+mypy clean. Tagged phase-06-complete. |
| 7 | Knowledge base & RAG | ✅ | Backend: knowledge module (KB CRUD, document upload file/url/text → store + Celery enqueue), `app/rag` pipeline (loaders PDF/DOCX/CSV/TXT/MD/URL+SSRF, recursive char chunker, Ollama embeddings + resolver, vector + hybrid-RRF retrieval, context assembly w/ char/token budget), Celery worker running `rag.ingest_document`, RAG wired into playground (prompt assembly + streamed `citations` event), migration 0004 (HNSW + GIN indexes). Frontend: knowledge list/detail wired to real API (upload/url/text, live status polling, chunk viewer, reingest/delete) + builder Knowledge tab (real KBs, enable-RAG, retrieval test). **Verified live (Playwright + curl): browser upload→Celery worker→real Ollama `nomic-embed-text` embeddings→ready→chunk viewer; builder retrieval test returns the correct chunk; playground stream emits a `citations` event then a grounded answer from local `qwen3:14b`.** 79 tests pass; ruff+mypy clean. |
| 8 | Chat persistence & memory | ✅ | Backend: `app/chat` (assembly, TurnResult runtime, memory summarizer on a small configurable model), shared `app/rag/agent_retrieval`, conversations module (`POST /v1/agents/{id}/chat` SSE+JSON persisting conversations/messages w/ usage/cost/latency/citations; list/detail/messages/patch/delete; long-term memory folds aged-out turns into `memory_summary`), WebSocket `WS /v1/agents/{id}/chat/ws`. Also fixed the published-agent silent-save bug (branch-on-edit, ADR-023). Frontend: `/conversations` two-pane browser + streaming composer through the persisted endpoint; nav item. **Verified live: curl + browser — streaming `conversation`/`token`/`message` events, continuation on the same conversation, persisted history renders, composer streams a persisted turn.** 87 tests pass; ruff+mypy clean. |
| 9 | Tools & tool calling | ✅ | Backend `app/tools`: built-ins (get_datetime, calculator, knowledge_search, guarded http_request w/ SSRF, web_search stub) each JSON-schema'd; user-defined HTTP tools (templated `{{arg}}`, SSRF-guarded, timeouts); Tool CRUD + `/test` + `/runs`; `run_turn` tool-calling loop (iteration-capped, execute→feed-back→continue) wired into persisted chat + playground; every call logged to `tool_runs`. Frontend: builder Tools tab wired (enable-tools, built-in toggles, HTTP tool builder + test, runs view). **Verified live: qwen3:14b called the `calculator` tool mid-conversation ("47 × 89" → tool run `{expression:"47 * 89"}`→`4183`, used in the answer), and the Tools tab shows the built-in toggled on + the real run.** 97 tests pass; ruff+mypy clean. |
| 10 | n8n integration | ✅ | Backend `app/integrations/n8n_client` (list/get workflows via public API, HMAC-signed `trigger_webhook`, `verify_callback` w/ replay protection, webhook-URL extraction). `type="n8n"` tool slots into the Phase-9 dispatch/loop (ADR-024): **sync** (Respond to Webhook → fed to model) + **async** (callback resolves a pending `tool_run`). `/v1/tools/n8n/{workflows,bind,callback}`. Starter workflows in `infra/n8n/` + import README. Frontend: `/automations` lists real workflows + bind-as-tool dialog (agent + mode). **Verified live end-to-end: created+activated the echo workflow in the running n8n, bound it, and qwen3:14b called it — the real webhook responded `{received:{message:"n8n works"}}` and the model used it.** 106 tests pass; ruff+mypy clean. |
| 11 | Web widget | ✅ | Backend `app/modules/public`: `GET /config`, `POST /chat` (SSE + JSON, rate-limited, optional visitor identity, no dashboard auth) + `WS /ws`, keyed by `public_key`; reuses the dashboard runtime (refactored `build_tooling`/`_resolve_provider`/`_finalize_turn` to be org-context-free). `packages/widget`: single dependency-free `widget.js` (Shadow DOM, launcher, streaming, sanitized markdown, quick replies, file attach, theming, `window.BotForge` SDK) → served at `/widget.js`. Frontend: builder Channels tab (color/position/launcher/mode/branding → `persona.widget`, autosaved) with live preview + copyable embed snippet. **Verified live: embedded the snippet on a plain HTML page — the widget loaded its themed config and `BotForge.sendMessage()` streamed a reply from the public endpoint (Shadow-DOM isolated, cross-origin).** 110 tests pass; ruff+mypy clean. |
| 12 | Messaging channels | ✅ | `app/channels`: a `BaseChannel` adapter interface + registry; Telegram (setWebhook + secret-token verify), WhatsApp (GET verify challenge + `X-Hub-Signature-256`), Slack (v0 signature + `url_verification` + `chat.postMessage`), Discord (Ed25519 interaction verify + PING/PONG + inline slash-command reply). Channel CRUD with **encrypted, masked** tokens; the shared inbound turn factored into `app/chat/inbound.InboundTurn` (also honours handoff-pause). Frontend Channels tab: per-channel connect flows (token entry, enable/disable, webhook URL). **Verified live: a signed Telegram inbound webhook produced a real Groq reply ("Paris.") on a `channel="telegram"` conversation.** Real provider *delivery* is mock-tested (this env can't reach provider hosts / has no public webhook URL). 117 tests pass; ruff+mypy clean. |
| 13 | Inbox & handoff | ✅ | Handoff triggers (keyword in `app/chat/handoff` + a `request_handoff` built-in tool) pause the bot (`InboundTurn` honours `status="handoff"`); `handoffs` records; inbox endpoints (list/detail/takeover/handback/reply/assign/close/notes/tags); an in-process pub/sub (`app/realtime/hub`) drives the operator inbox WS **and** a widget listen-socket so operator replies reach the end user live. Two-pane Inbox UI wired + realtime. **Verified live end-to-end in the browser: widget user asks for a human → canned handoff message → appears in the inbox → operator takes over + replies → the reply pushes to the widget live → handback → bot resumes.** 123 tests pass; ruff+mypy clean. |
| 14 | Analytics & metering | ✅ | `app/modules/analytics`: overview (conversations/messages/users/tokens/cost/handoff+resolution rate), usage grouped by day/provider/model, latency (p50/p95/avg via `percentile_cont`), top-questions, unanswered (escalation heuristic), CSV export — all aggregated **live from `messages`/`conversations`/`handoffs`** (org-scoped). `app/worker/rollup`: Celery task upserting `usage_records` + refreshing `quotas` with a threshold event. Frontend: `/analytics` + dashboard stat row/chart wired to real aggregates. **Verified live against real Groq usage: the UI/overview (51 msgs, 3789+956 tokens) matches a direct `messages` aggregate exactly, and the rollup's `usage_records` matches the message sums.** 129 tests pass; ruff+mypy clean. |
| 15 | API keys/webhooks/audit | ✅ | `app/modules/apikeys`: `bf_`-prefixed keys (hashed + prefix lookup, scopes, last-used), and `current_org` now accepts an API key (`X-API-Key` / `Bearer bf_…`) resolving its org + acting as the creator. `app/webhooks`: endpoint CRUD (encrypted/masked secret), HMAC-signed delivery with retry/backoff + delivery log, and the full event catalog emitted across the app (message.created, conversation.created/closed, handoff.requested/resolved, document.ready/failed, tool.run, usage.threshold). `app/modules/audit`: read API; `app/core/audit.write_audit` records sensitive mutations. Frontend: wired settings pages (API keys, webhooks + deliveries, audit) + a `lib/rbac` matrix / `useCan`. **Verified live: API key authenticates requests; a real chat emits a `message.created` delivery; `/test` signed-delivered to example.com (405); audit recorded key/webhook creation; a viewer got 403 on admin actions + a read-only UI.** 141 tests pass; ruff+mypy clean. |
| 16 | Guardrails & hardening | ✅ | **16.1** `app/chat/guardrails`: retrieved RAG chunks + tool output are neutralized (`neutralize_injections`) and wrapped as **data, not instructions** before the model sees them; blocked-topics (`persona.blockedTopics`) refuse pre-LLM via a `RefusalProvider`; output redaction strips secret-looking strings from stored/returned text. **16.2** API-key **scope enforcement** (effective role = scope tier capped by creator's role, least privilege; `admin`≠`owner`), rate limits on channel webhooks + n8n callback, `SecurityHeadersMiddleware` (CSP/XFO/nosniff/Referrer/COOP/CORP/Permissions + prod HSTS), advisory `pip-audit`+`npm audit` CI job, and a verified `docs/SECURITY.md` checklist. **16.3** perf harness (`infra/perf/{locustfile,measure}.py`). **Verified live: blocked topic → fallback (not the model), secret → `[redacted]`, a read-scoped key → 403 on write / 200 on read. Measured NFR-1 (see below).** 151 tests pass; ruff+mypy clean. |
| 17 | Admin console | ✅ | **17.1** platform-staff API (`app/modules/admin`, `require_staff`/`is_staff`, org-agnostic — no `X-Org-Id`): `GET /v1/admin/{orgs,users,usage,health,feature-flags}` + `PUT /v1/admin/feature-flags/{key}` (Postgres upsert). New `FeatureFlag` model + migration `0005`. **17.2** `/admin` console UI (platform usage cards, live system-health pills, top-orgs, feature-flag toggles, orgs + users tables), a `is_staff`-gated "Platform › Admin" sidebar item, and a client route guard + middleware. **Verified live (curl + Playwright): staff → 200 + full console; non-staff → 403 on every endpoint **and** redirected off `/admin` to `/dashboard` with no Admin nav; unauth → 401.** 157 tests pass; ruff+mypy clean. Tagged phase-17-complete. |
| 18 | Billing (optional) | ⏸️ | **DEFERRED** — optional/stretch in the spec (PRD §7, Phase 18 header), no `STRIPE_SECRET_KEY`/`STRIPE_WEBHOOK_SECRET` supplied, and the platform is not monetising yet. Metering plumbing (`usage_records`, `quotas`, `subscriptions` table, `Organization.plan`) already exists, so billing can be layered on later without rework. Not built. |
| 19 | E2E/docs/polish | ✅ | **19.1** Playwright E2E — one spec per PRD §6 criterion 1–7 (`apps/web/e2e`), driven against the real stack with the Fake provider (`LLM_FORCE_FAKE`), **all 7 green**; new CI `e2e` job boots services + runs them (closes the Phase-0 Playwright item). Also the **Next.js 14→16 + React 18→19 + ESLint 9** upgrade (**0 npm-audit advisories**, was 4 high + 1 moderate) and a real **worker bug fix** (NullPool engine so async tasks survive across Celery loops). **19.2** README + self-host / API-usage / widget-install / n8n-setup guides; widget-demo.html rewritten. **19.3** axe a11y gate (spec 08) on key pages + widget — fixed widget accent contrast + `--faint` token. Throwaway `@example.com` dev rows + `live_demo` flag cleaned (`make clean-devdata`). 157 backend tests pass; ruff+mypy+tsc+eslint clean. Tagged phase-19-complete. |
| 20 | Production deployment | ✅ | **20.1** `docker-compose.prod.yml` (Caddy auto-TLS for `$DOMAIN`+`$API_DOMAIN`, non-root api+web images, healthchecks, **one-shot migrate job** so replicas never re-migrate, nightly backup service) + a production **web Dockerfile** (Next standalone, non-root). **Realtime hub → Redis pub/sub** (ADR-028, same interface, cross-node delivery test). **Webhook retry beat sweep** (`webhooks.sweep_pending` + beat service). **Refresh token → httpOnly cookie** via a Next BFF (`/api/auth/*`, ADR-019); access token stays JS-readable by cross-origin+WS architecture (documented). **20.2** `pg_dump` backup + restore scripts, **`/metrics`** (Prometheus), **Sentry** hook, JSON-log aggregation. **20.3** K8s manifests (`infra/k8s/`). **20.4** `release.yml`: build+push images to GHCR + **smoke-test `/readyz`** on the built image + deploy template. 162 backend tests pass; ruff+mypy+tsc+eslint clean; **10/10 Playwright E2E green**. Tagged phase-20-complete. |

Legend: ⬜ not started · 🟨 in progress · ✅ complete · ⏸️ deferred

## Measured performance (NFR-1, Phase 16.3 — `infra/perf/measure.py`, live stack 2026-07-19)
- **Non-LLM API** `GET /v1/agents`: **p50 13 ms, p95 16 ms** (n=30) — well under the 300 ms target.
- **LLM first-token (Groq `llama-3.1-8b-instant`)**: **p50 417 ms, p95 529 ms** (n=7) — meets NFR-1.
- Measured **Groq separately from Ollama** on purpose: the earlier "p95 166 s" figure was **local
  Ollama `qwen3:14b` tool-calling turns** (30–90 s/turn), not a web-provider latency — it must not
  be blended into the Groq number. Ollama is excluded from the NFR-1 first-token figure by design.

## Shipped enhancements (post-v1)
- **n8n workflow discovery is scoped to the owning org (2026-07-30).** `list_n8n_workflows` had
  **no tenant filtering whatsoever** — it returned every workflow in the shared n8n instance to
  every org. Each client's Automations page listed every other client's automations, and
  platform-internal workflows (`SHARED — Master Router`, the auto-provisioner) were bindable as a
  client's agent tool. This is the one multi-tenancy hole that the org-scoped repository base
  couldn't catch, because the data lives in n8n rather than in Postgres, so no query was ever
  filtered by `organization_id`. Found from a **live screenshot of the Automations page**, not
  from a test: no test had ever put two orgs' workflows in one n8n instance, so nothing failed.
  New `tools/service.workflow_visible_to_org(tags, name, org_slug)` keyed on n8n **tags**: tagged
  with an org's slug → visible only to that org; tagged `internal`/`shared-internal`/
  `platform-internal` → hidden from every org unconditionally; untagged → visible to all.
  The asymmetry is deliberate — the untagged default is **permissive** so the operator's existing,
  not-yet-tagged client workflows didn't disappear the moment this shipped, while the internal
  direction **fails closed**, because a client reaching an admin workflow is a security incident
  rather than a UX gap. A `name.startswith("SHARED —")` check covers the internal workflows that
  predate tagging; tagging them `internal` retires it. The same check runs in `bind_n8n_workflow`
  when binding by `workflow_id` (typed `tools.n8n_forbidden`, 403), closing the hole where an org
  could bind a workflow it was never shown just by knowing or guessing its n8n id.
  **Not covered, by design:** binding by a pasted webhook URL — a caller already holding the secret
  URL can reach it like any other endpoint. Treat client webhook URLs as secrets. See ADR-040 and
  `docs/guides/N8N-SETUP.md §5`. 4 backend tests (tag extraction, the visibility matrix, a
  two-org discovery list, and a cross-org bind rejected).
  **Operator action required — the fix is inert until workflows are tagged.** Audited live against
  both instances on 2026-07-30: on the AUROZEN n8n (`:5678`) **6 of 9** workflows are still
  untagged and therefore visible to every org — `00001 — Load KB`, `00001 — Main Agent`,
  `00002 — Load KB`, `00002 — Main Agent`, `Website Lead — Contact Form` and
  `BotForge — Echo (sync)`; the three `SHARED — …` ones are already hidden by the name rule. On
  BotForge's own n8n (`:5679`) all three are untagged (`Acme Co`/`Globex Inc` starter automations
  and the `TEMPLATE`, which should be `internal` so no client can bind it).
- **One-command client provisioning (2026-07-30).** `scripts/provision-client.mjs` takes
  `--name` / `--email` / `--plan` and stands a client up end to end: org → agent (starter
  persona, Groq `llama-3.3-70b-versatile`, tools on) → **published** so it's live before the
  client's first login → the n8n starter automation cloned + activated + bound as a tool →
  client invited as `editor`. Zero npm dependencies (Node 18+ `fetch`), so there's nothing to
  install before provisioning. Plus `infra/n8n/template-starter-automation.json`
  (`TEMPLATE — Starter Automation`: Webhook → Set → Respond to Webhook) as the thing it clones.
  Verified live: two back-to-back runs with the same `--email` produced **6 reuses and 0
  creations** (one org, one agent, one invitation, one tool confirmed by SQL), and a real chat
  turn made Groq call the tool — n8n executed and its response came back inside the
  conversation (`{"received": {"customer": "Globex", "order": "5512"}, "handled_by": "Globex
  Inc — Starter Automation"}`). 8 unit tests (`node --test`) over the naming/parsing helpers,
  where a bug means a cross-client collision rather than a crash; `make provision` /
  `make test-scripts` added.
  Design notes worth keeping: it **logs in as staff** rather than using a `bf_…` key, because
  org creation is gated on `User.is_staff` and no key scope grants it; it binds through
  `POST /v1/tools/n8n/bind` so the webhook URL is derived by the same code the runtime uses;
  and each clone gets its **own** webhook path (`{slug}-starter-automation`) — cloning the
  template verbatim would point every client's tool at one shared URL, so whichever workflow
  n8n resolved first would answer everyone, which is a cross-client leak rather than a mix-up.
  Two idempotency subtleties came out of testing: `create_invitation` only rejects an
  already-**active** member, so a blind re-run mints a second pending invite and emails the
  client twice (the script checks the pending list); and re-patching an existing agent forked a
  new draft every run via branch-on-edit (ADR-023) **and would have overwritten a client's own
  persona edits with the starter defaults**, so an agent that already has a system prompt is
  now left strictly alone — nor is its unreviewed draft published behind its owner's back.
  **Infra:** the bundled dev `n8n` service now takes `N8N_HOST_PORT` (default 5678, so the
  canonical setup is unchanged) and sets `N8N_DIAGNOSTICS_ENABLED=false` — n8n resolves
  `telemetry.n8n.io` at boot and *exits* when DNS fails, which is why `botforge-n8n-1` had been
  dead for two days on this machine. It now runs on **5679**, isolated from the unrelated n8n
  on 5678 that belongs to another project; BotForge creating and activating workflows in
  someone else's instance is not acceptable, so `.env` points at its own.
  **Still needs a human:** the n8n API key (n8n → Settings → API, with workflow
  read/list/create/update/activate scopes) and a staff account for
  `PROVISION_STAFF_EMAIL`/`PROVISION_STAFF_PASSWORD`.
  **Not done (deliberately, per the brief):** `docker-compose.prod.yml` still references
  `N8N_BASE_URL: http://n8n:5678` while defining **no `n8n` service** — provisioning against a
  prod stack needs that added first. Logged in the roadmap below.
- **Email actually gets delivered (2026-07-30).** `app/core/email.py` had exactly one backend —
  `ConsoleEmailBackend`, an in-memory outbox — and `get_email_backend()`'s `"smtp"` branch logged
  `smtp_backend_not_implemented` and fell back to it. So **no email this app sent had ever reached
  a real inbox**: not invitations, not signup verification, not password reset, not magic-link
  sign-in. All four already funnelled through one `send()` call, so this was a one-place fix.
  New `SmtpEmailBackend` over **aiosmtplib** (async — stdlib `smtplib` would block the event loop
  on every send). **Plain SMTP, not a provider SDK**: Resend/Postmark/SendGrid/Mailgun/SES all
  expose a relay taking the same five settings, so switching provider is an env change. TLS mode
  is derived from the port (465 = implicit, everything else = STARTTLS) because providers publish
  both and the flag they want isn't something an operator should have to know; TLS is never
  optional. Unset `SMTP_HOST`/`SMTP_FROM` raises a typed `email.not_configured` rather than
  dropping the message (CLAUDE.md §7) — a swallowed invitation looks exactly like a delivered one.
  New `app/core/email_templates.py` gives the four emails an HTML part (plain text alone reads as
  broken/spam in a modern inbox); the text part **keeps its `Token: …` line**, which is load-bearing
  — a dozen test files recover tokens by parsing it out of the console outbox.
  **Sending moved off the request path** onto a new `email.send` Celery task, and two real hazards
  turned up while verifying it live: (1) `.delay()` is blocking socket I/O, so on the event loop it
  would stall every concurrent request, not just its own; (2) against a dead broker kombu retries
  the connection 20× with 1s sleeps **regardless of `retry=False`**, which measured as a **30-second
  hung signup**. The enqueue therefore runs in a worker thread under a bounded
  `email_enqueue_timeout_seconds` (default 2s) and is abandoned on timeout — losing a queued email
  beats losing the signup that triggered it. Measured after the fix: 6.2s vs a 4.3s
  console-backend-with-dead-Redis control, i.e. ~2s of email cost, down from ~26s.
  Console mode still sends **inline**, deliberately not through eager Celery: eager tasks run in the
  caller's thread where `app/worker/tasks._run`'s `asyncio.run()` raises inside the already-running
  loop — the same trap that silently broke eager ingestion (CLAUDE.md §12). That's also what keeps
  the test outbox synchronous, so every existing email test is untouched.
  `SMTP_PORT=` ships blank in `.env.example`, which pydantic can't coerce to `int`, so a
  before-validator reads blank as the default 587 (ADR-020's blank-is-unset convention) — an
  unfilled placeholder must never stop the app booting. 18 backend tests.
  **Still needs a human:** sign up with an SMTP provider, verify the sending domain (SPF/DKIM), and
  fill in `SMTP_*`. No code can skip that — it's how Gmail decides the mail isn't spoofed.
  **Noticed, not fixed:** with Redis down, a signup takes ~4.3s even on the console backend — the
  rate limiter's Redis probe has no timeout before falling back to in-memory. Pre-existing and
  unrelated to email; logged in the roadmap below.
- **Invitations can actually be accepted (2026-07-29).** `accept_invitation()` was correct and
  complete server-side, but **nothing in the web app ever called it** — the email link had
  nowhere to land, so an invitation could never leave "pending" no matter what the recipient
  did. Added the landing page at **`/invitations/accept`** — the path the invitation emails
  have always pointed at, so already-sent invites work — outside the authenticated `(app)`
  layout, since an invitee usually has no account yet. If signed in it redeems immediately;
  otherwise it offers signup *or* login and continues straight to accepting rather than
  dropping them on the dashboard having silently failed to join. The three server-modelled
  failures each get their own explanation: expired/invalid, wrong email, org deleted. On
  success the joined org is set active. 5 Playwright checks, including a brand-new user
  going from email link to active membership.
- **Widget appearance is unversioned and always live (2026-07-29).** `_theme()` read
  `persona.widget` off whatever `_live_version()` resolved — the same published-vs-draft unit
  as behaviour — so a colour change waited behind a publish approval. It only *looked*
  instant in testing because a never-published agent's latest draft and its live version are
  the same thing by coincidence; with a real publish history it would have got stuck. New
  `widget_configs` table (migration `0014`, one row per agent, **no version**), seeded from
  the version actually being served today — the published one if there is one, else the
  newest draft, since picking wrong would silently restyle a live widget. `_theme()` now
  reads it by `agent_id`, bypassing `_live_version()` entirely. New
  `GET/PATCH /v1/agents/{id}/widget-config` gated on `AGENTS_WRITE`, never `AGENTS_PUBLISH` —
  making a client wait for review to fix their own branding would be absurd. Merge-on-write
  preserved. Runtime behaviour (live fetch, CSS variables, preview postMessage) unchanged.
  7 backend tests; the widget E2E now asserts the change goes live **with no publish step**.
- **Editing and publishing are separate permissions (2026-07-29).** `AGENTS_WRITE` covered
  both saving a draft and putting it live — one permission for two very different levels of
  risk. New `AGENTS_PUBLISH` gates publish/rollback; `owner`/`admin` have both. **`editor` is
  now the client role**: edit drafts, manage knowledge, connect their own Meta credentials
  (`TOOLS_MANAGE` was already separate), work the inbox, and test in the Playground — but not
  publish. The draft/publish machinery itself is untouched; only who may pull the trigger.
  The builder shows "Awaiting review" instead of Publish for those roles, and the admin
  console gains an **"Awaiting review" column** per org (agents never published, or whose
  newest draft is past the live version) so staff notice waiting work without opening every
  builder. 6 backend tests.
- **CRM auto-capture with cross-channel identity (2026-07-29).** The "cross-channel merging
  belongs on top of this table" extension `Contact`'s own docstring anticipated. New
  `CrmContact` (migration `0013`) is the canonical *person*; `Contact` stays per-channel and
  gains `crm_contact_id`. `lead_stage`/`order_status`/`notes`/`labels` moved off `Contact`
  onto it (they describe the human, not a handle), with a backfill so no operator's data was
  lost. **Extraction is gated**: a free regex pass answers "is there anything email- or
  phone-shaped here?", and only then does one small-model call run — over just that message,
  reusing the memory summarizer's provider pattern — to pull out an associated name and tidy
  formatting. The regex result is the floor, so a useless model reply still keeps real data.
  **Identity resolution matches on email or phone only, never name** — names collide, and a
  wrong merge silently mixes two customers' histories. Normalisation (lowercased email,
  digits-with-`+` phone) is what makes the same detail written three ways match itself.
  Learning fills blanks only, so an operator's correction isn't overwritten by a later guess.
  Org-level `auto_crm_capture_enabled`, **on by default with an off switch** on Settings.
  The hook lives in `_persist_user_message`, the one place every inbound path funnels
  through — including messages sent while a human has taken over, which never reach a bot
  turn. 14 capture tests, 15 CRM tests, 3 Playwright checks.
  **Behaviour change worth knowing:** the CRM lists people, so a visitor who never shares an
  email or phone no longer appears there — they remain in the Inbox as a per-channel handle.
  A CRM full of `anon-9f2c` rows would help nobody, but this is a visible difference.
- **Contacts → CRM, plus manual contact creation (2026-07-29).** Nav item and page title
  renamed to "CRM"; the `/contacts` route is unchanged, so the Inbox's contact link still
  resolves. New `POST /v1/contacts` adds the first **operator-initiated** creation path —
  every other row in this table is upserted by an inbound message. A manual contact has no
  platform account behind it, so it gets `channel="manual"` and a generated `external_id`,
  keeping the `(org, channel, external_id)` uniqueness constraint meaningful rather than
  special-casing it. `manual` joins `dashboard`/`api`/`web` in `channel-meta.ts`'s
  `REPORTING_ONLY` map, so it can never become an Inbox tab — it has no webhook and no
  conversations at all. 4 backend tests.
- **URL ingest extracts the article, not the page chrome (2026-07-29).** `strip_html()`
  removed `<script>`/`<style>` then regex-stripped every remaining tag with no notion of
  document structure, so nav menus, headers, footers and cookie banners landed in the same
  text stream as the content. On `https://docs.n8n.io/` the nav ("Forum Changelog Get started
  Deploy Build Nodes Connect Administer Contribute") *opened* the extracted text and
  dominated the first chunk — the chunk retrieval most often returns. Added **trafilatura**
  and a new `extract_main_content()` used by `load_url()`, with `strip_html()` kept as the
  fallback for pages it can't parse (a stub still ingests rather than failing). Markdown
  output preserves headings, which the recursive chunker splits on, so chunks land on section
  boundaries. The real docs.n8n.io page is committed as a test fixture — one test pins the
  *old* broken behaviour so the file documents what was wrong, others assert the nav is gone
  and the first chunk is content. 8 tests.
- **Creating an organization is staff-only (2026-07-29).** BotForge is run as one org per
  client, provisioned for them — not a self-serve product where anyone spins up as many as
  they like. A client seeing "New organization" invites an empty, confusing second org.
  `OrgSwitcher` now gates the create item + dialog on `is_staff` (the same
  `useSession((s) => Boolean(s.user?.is_staff))` pattern the Admin nav item uses); the
  switcher itself stays visible, and **switching between orgs you were invited to keeps
  working** — an agency may reasonably invite one person into several client orgs.
  **Enforced server-side too**, since hiding a button doesn't stop a direct API call:
  `POST /v1/orgs` returns a typed `orgs.create_forbidden` (403) when a non-staff user
  already belongs to an org. The **first** org is always allowed — signup's create-first-org
  step comes through the same endpoint and a brand-new user obviously isn't staff — and the
  count ignores soft-deleted orgs, so deleting your only org doesn't strand the account.
  Membership via *invite* counts too: the gate is "has an org", not "created one".
  5 backend tests, 5 web unit tests.
- **Team performance reporting (2026-07-29).** The analytics module reported on channels,
  providers and models — never on *people*. New `agent_performance()` +
  `GET /v1/analytics/agents` groups by `Handoff.assigned_to` and reports handoffs handled,
  average first-response time (first `provider="operator"` message minus the handoff's
  creation), average resolution time, and conversations closed. **No new tracking was added**
  — every input already existed. Durations are `None`, not `0`, when there's nothing to
  average: a teammate who has never resolved anything hasn't achieved a 0ms resolution time,
  and the UI renders that as an em dash. Operator messages that predate a handoff are excluded
  from the response average (they belong to an earlier handoff on the same conversation), and
  unassigned handoffs are attributed to nobody. A "Team performance" section on the Analytics
  page reuses the per-channel breakdown's visual language. 6 backend tests, 7 web unit tests,
  2 Playwright checks.
- **Campaigns — proactive widget messages (2026-07-29).** `campaigns` (migration `0012`) with
  two kinds. **`widget_trigger` ships live**: an active campaign rides the existing public
  config, and the widget schedules it client-side — fires once per visitor per campaign
  (sessionStorage), only on URLs matching an optional pattern, and **never once a real
  conversation has started or the panel is already open** (an unprompted message on top of
  someone's in-progress chat is an interruption, not a greeting). Delay is bounded 3–3600s:
  firing on page load reads as a popup ad. **`broadcast` is draft-only by design** — the model
  and UI exist but activating one is refused with a typed error until consent tracking, an
  unsubscribe path and rate-limited batch sending are built (ADR-039). Builder section on the
  Channels tab. 6 backend tests, 3 Playwright checks (including the real widget bundle opening
  itself on a plain page).
- **Help Center (2026-07-29).** Public-facing articles, deliberately a **separate store from
  the RAG Knowledge module**: Knowledge is retrieval material for the model, this is prose a
  human reads. `help_articles` (migration `0011`, slug unique per agent since slugs address
  articles in public URLs); authenticated CRUD at `/v1/help-articles`; unauthenticated
  `GET /v1/public/agents/{key}/help[/{slug}]` mirroring the widget-config pattern — a draft
  404s exactly like a non-existent article, so unpublished titles can't be enumerated.
  Authoring UI at `/knowledge/help-center` (plain `<textarea>`; no editor dependency), public
  pages at `/help/{agentKey}[/{slug}]` outside the authenticated layout. **Opt-in RAG sync**
  per article: publishing with "Also teach the AI" pushes the body into a knowledge base the
  agent *actually retrieves from* — targeting an unread KB would look like it worked and
  change nothing, so an agent with no RAG source gets a typed error instead. Editing replaces
  the synced document rather than accumulating a stale copy, and unpublishing removes it (the
  AI shouldn't answer from something a human can no longer read). Markdown rendered by a small
  in-repo subset renderer that **escapes before formatting**, so raw HTML in a body can never
  become live markup. 7 backend tests, 7 renderer unit tests, 3 Playwright checks.
  Also adds `/contacts` to the auth guard — it was missed when that page shipped earlier today.
- **Contacts / CRM (2026-07-29).** Extends the existing `Contact` (from the unified-inbox work)
  rather than introducing a second contact concept: `lead_stage`, `order_status`, `notes`,
  `labels` (migration `0010`, + a GIN index on labels and a composite on `(org, lead_stage)`
  for the list filters). `notes` and `labels` deliberately mirror `Handoff.notes`/`.tags`
  shapes so both timelines render the same way. New `/v1/contacts` module: paginated list
  searchable by **name or platform id** (an operator searching a phone number means the phone
  number), filterable by stage/label/channel; detail joins the contact's conversations;
  PATCH for stage/order status, PATCH for labels, POST for notes. `lead_stage` is a fixed
  funnel — free text would fragment into `qualified`/`Qualified`/`QUALIFIED` and break the
  filter — while `order_status` stays free text because what counts as one is
  business-specific. New `/contacts` page (table + detail panel reusing `ContactAvatar` and
  the inbox's card style), a `Contacts` nav item under Operate, and the inbox thread header
  now links the contact through to `/contacts/{id}`. 9 backend tests, 2 Playwright checks.
- **Macros (2026-07-29).** A named, ordered list of inbox actions (`reply` / `add_tag` /
  `assign` / `resolve`) run against one conversation in a click — model + migration `0009`,
  CRUD at `/v1/macros`, execution at `POST /v1/inbox/conversations/{cid}/macros/{id}`.
  Execution **reuses the same inbox service functions the manual buttons call**, so a macro
  can't drift from what those do (RBAC, webhook events, realtime publishes included).
  Atomic in two layers: every step is **validated before any is applied** — a DB rollback can
  undo a tag but cannot un-send a WhatsApp message, so a deleted canned response or a
  departed teammate fails while the conversation is still untouched — and execution is then
  wrapped in a SAVEPOINT. `add_tag` merges rather than replacing, and re-running doesn't
  duplicate. Per-action params are validated at *save* time, so a half-formed macro can't be
  stored and discovered later by an operator. Builder UI with reorder/remove; a Run macro
  dropdown in the thread header that stays hidden until the org has one. 8 backend tests,
  3 Playwright checks.
- **Canned responses (2026-07-29).** Org-scoped reply snippets (`canned_responses`, migration
  `0008`, unique per `(org, shortcut)` — shortcuts are typed rather than picked, so a duplicate
  would make the picker ambiguous). CRUD module at `/v1/canned-responses`; reading needs only
  `READ` (every operator needs them to reply), writing needs `INBOX_HANDLE`. Settings page for
  create/edit/delete. In the inbox composer, typing `/` opens a filtered picker — the trigger
  only fires at the start or after whitespace, so `example.com/refunds` and `24/07` don't
  misfire it — with arrow-key/Enter/Tab selection, and insertion replaces the trigger text
  rather than appending. 8 backend tests, 9 web unit tests, 2 Playwright checks.
  **Also fixes a pre-existing 500**: any endpoint whose Pydantic `field_validator` raised
  `ValueError` returned `internal_error` instead of a 422, because Pydantic puts the raised
  exception in the error's `ctx` and the handler json-encoded the raw list. Widget-config
  writes were affected long before this feature existed.
- **WhatsApp 24-hour customer-service window (2026-07-29).** A silent-failure bug, not a
  missing feature: `send()` fired free-form text with no awareness of Meta's window, so a
  reply sent more than 24h after the customer's last message was rejected (error `131047`)
  and simply never arrived — while sitting in the transcript looking sent. Adds
  `Conversation.last_inbound_at` (migration `0007`, backfilled from the newest `role="user"`
  message) kept **separate from `last_message_at`**, which moves on our own outbound too and
  would have made a bot reply look like customer activity and falsely re-open the window. New
  `BaseChannel.check_can_send()` hook — overridden only by WhatsApp — is called *before* the
  message is persisted, so a refusal leaves no phantom message; it raises a typed
  `whatsapp_window_closed` (409) per CLAUDE.md §8 instead of a swallowed no-op. Meta's own
  `131047` is honoured too, in case our clock disagrees. `send_template()` posts
  `type: "template"` with positional body params; approved names live on `Channel.config`
  (`templates`, comma-separated — Meta approval is a Meta-side process BotForge can't do).
  `InboxDetail.send_window` reports `{open, closes_at, templates}` (null on channels with no
  such limit), and the composer swaps the free-text box for a warning + template picker when
  it's shut. 7 backend tests, 3 Playwright checks.
- **Inbox shows every channel tab, connected or not (2026-07-29).** Reversal of a deliberate
  choice from the 07-28 inbox build: tabs were filtered to connected channels only, which hid
  exactly the platforms a user still needs to set up and made discovery depend on already
  knowing the builder's Channels tab exists. Now `inboxChannelTabs()` returns all 7
  unconditionally (replacing `visibleChannelTabs`), and the new `isChannelConnected()` drives
  *styling* instead of presence: an unconnected tab is dimmed with a hollow dot and an
  `aria-label` of `"{Channel} (not connected)"`. Selecting one replaces both panels with
  `"{Channel} isn't connected yet."` + a **Connect {Channel}** button — kept deliberately
  distinct from the connected-but-quiet `"Nothing in the inbox yet."`, since a channel that
  can't receive at all is a different situation from one that simply hasn't. **The credential
  form is not duplicated**: channels belong to an agent while the inbox spans the org, so the
  button resolves the target agent first (straight through when there's one, a picker when
  there are several, a create-agent prompt when there are none) and deep-links to
  `/agents/{id}?tab=channels&connect={type}`; `MessagingChannels` reads that param on mount,
  opens the existing `ConnectDialog`, and strips it so a reload doesn't reopen it. 11 web unit
  tests + 2 Playwright flows; analytics' channel breakdown is untouched.
- **Per-channel analytics — Dashboard + Analytics breakdown (2026-07-28).** With up to 7 channel
  types per agent, analytics had no channel dimension at all: `usage()` grouped only by
  day/provider/model and `overview()` returned one flat aggregate. **Backend**
  (`modules/analytics/`): new `ChannelBucket` + `Overview.by_channel`, `group_by=channel` on
  `usage()`, a `channels` CSV export kind, and a `channel=` filter param on every analytics
  endpoint. The channel set is the **union of channels with traffic and channels that are
  connected** — a plain `GROUP BY channel` would drop a live-but-silent channel, which is
  exactly the case that matters when WhatsApp/Instagram go live days before the first real
  message. `widget` is always included (every agent has the embeddable chat inherently, so it
  has no `channels` row to enable — the same rule the inbox tab bar follows); disabled channels
  are excluded. Rates guard the zero-conversation case. **Frontend:** one `ChannelBreakdown`
  component shared by the Dashboard and the Analytics page (icon + label from the existing
  `channel-meta` map, conversations with a proportional bar, resolution rate, cost), a "Tokens by
  channel" bar list, and an "Export channels" CSV control. A connected-but-empty channel renders
  as a flagged zero row with an em dash for its rate — `0%` resolution reads as failure rather
  than silence. `dashboard`/`api`/`web` got real labels (they're genuine conversation channels
  but never inbox tabs) instead of falling back to "Other". 5 backend tests, 9 web unit tests,
  1 Playwright flow covering one populated + one connected-but-empty channel across the
  Dashboard, the Analytics page, and the CSV. No migration — grouping by an existing column.
- **Unified multi-channel inbox — contacts, Instagram + Messenger, channel tabs (2026-07-28).**
  The inbox could previously only show a raw `channel_user_id`; it now shows a person, per
  channel. **Contacts** (`models/contacts.py`, migration `0006_contacts`): a `contacts` table
  unique on `(organization_id, channel, external_id)` + `conversations.contact_id`, with one
  upsert helper (`app/contacts/service.py`) used by every inbound path including the widget's
  `Visitor`. Names/avatars refresh with `COALESCE(new, old)` + a JSONB merge, so a payload that
  omits a name never erases one we had. Adapters supply identity inline
  (`InboundMessage.profile` — Telegram, WhatsApp) or through a new optional
  `BaseChannel.fetch_profile` hook, called only while the contact still lacks a name or avatar.
  **Instagram + Facebook Messenger** (`channels/instagram.py`, `facebook.py` over a shared
  `meta_messaging.py`): Meta unified the Send API, so one implementation covers both; the
  `X-Hub-Signature-256` check and `hub.challenge` handshake were factored out of `whatsapp.py`
  into `meta_signature.py` so all three Meta surfaces share one verification path. Deliveries
  are matched on the webhook `object` (`page` vs `instagram`), and echoes/read receipts are
  ignored. Profiles come from the Graph API. **Inbox API:** nested `contact` on
  `InboxItemOut`/`InboxDetail` (batched, no N+1) and a `?channel=` filter so tabs page
  server-side. **Inbox UI:** a channel tab bar — Web Chat always (the widget needs no
  connecting), every other tab only once that channel has an enabled row in the org
  (**superseded 2026-07-29: all 7 tabs now always render**, see the entry above), plus a
  "New" badge for the first week — and contact avatars with a platform badge in both the list
  row and the thread header. 9 backend tests, 12 web unit tests, 1 Playwright flow. New human
  secrets documented: `META_PAGE_ACCESS_TOKEN`, `INSTAGRAM_PAGE_ACCESS_TOKEN` (+ ids and a
  shared `META_VERIFY_TOKEN`); unset → warn and skip sending, inbound still works. Public
  **post-comment moderation is deliberately not included** (ADR-037). See ADR-036/037/038.
- **Widget customization → full parity (2026-07-21).** Extended the embeddable widget from
  accent/text/position to a complete design system, all flowing through the existing
  live-fetched public config (`GET /v1/public/agents/{key}/config`) so the embed snippet never
  changes. **Backend** (`modules/public/schemas.py` `WidgetTheme` + validated `WidgetConfigIn`,
  `modules/agents/service.py`): `widget_style` (solid|transparent), 4 colors
  (background/text/bubble/typing-area), `font_family` (5 system-safe stacks, no webfonts),
  `floating_button_style` (6 designs) + independent `floating_button_color`, `logo_url`,
  `input_bar_buttons` (attachment|emoji) — all nullable (unset = today's look), hex/enum
  validated with typed errors, **merge-on-write** so a partial PATCH never nulls sibling keys.
  **Logo upload** (`POST /v1/agents/{id}/widget/logo`) reuses the KB upload storage; rejects SVG +
  double-checks MIME **and** extension, 2 MB cap; served public + cross-origin at
  `GET /v1/public/agents/{key}/widget-logo`. **Widget bundle** (`packages/widget`): rewritten to
  apply everything via CSS custom properties (no per-agent rebuild), 6 inline-SVG launcher designs,
  `pulse-ring` keyframes gated behind `prefers-reduced-motion`, transparent frosted-glass style,
  emoji picker, and a `data-preview-mode` that live-applies posted config. **Builder** (`channels-tab`):
  full customization UI + a **real-widget iframe preview** driven by `postMessage` (not a CSS mock),
  reusing the debounced autosave. 4 backend tests + 2 Playwright checks (live embed reflects a
  saved change without re-pasting the script; builder preview applies a posted config instantly).
  No new env var (file storage reuses `UPLOAD_DIR`). See ADR-035.
- **Widget customization — parity fixes (2026-07-21).** Follow-up after a live comparison:
  (1) **bug** — the preview widget force-opened on every control change (`rebuildForPreview` did a
  full teardown + `api.open()` per `postMessage`). Split `build()` (once) from `applyConfig()`
  (in-place, preserves `state.open`, never force-opens); preview now starts **closed** like a real
  embed. (2) Transparent style uses its **own glass palette** (no solid header bar, white-glass bot
  bubbles + fixed near-black text, dark floating input pill), not "theme + blur". (3) The launcher
  picker previews the **real widget SVGs** (`lib/widget-icons.tsx`), not Lucide stand-ins. (4) The
  Channels tab renders **full-width** (drops the Playground column it doesn't need). (5) A
  builder-only **preview backdrop** swatch (local state, applied to the preview page via
  `postMessage`, never persisted). Regression tests: a config change never changes the panel's
  open/closed state; the transparent header has no solid backdrop. Widget still one file. See ADR-035.
- **Widget mobile-collision bug fix (2026-07-21).** On viewports under 768px the floating launcher
  and the fullscreen panel shared the same `z-index`, so an open panel painted over the launcher
  and could swallow clicks meant for the send button (a real bug for phone visitors). `api.open`/
  `close` now toggle a `bf-open` host class and `@media (max-width:767px){:host(.bf-open)
  .bf-launcher{display:none}}` hides the launcher while open at phone widths, relying on the panel's
  own header close button; ≥768px the launcher stays visible and still doubles as close. Playwright
  covers both breakpoints. (The preview-layout widening from the same original change was reverted
  per request; only the bug fix was re-applied.)
- **Widget preview single-host + sidebar flex fix (2026-07-27).** (1) A reported preview "overlap"
  (a white panel + dark launcher behind the themed one) was diagnosed live in the real Channels tab
  (Playwright): exactly **one** `#botforge-widget` host — not a duplicate mount. Hardened `widget.js`
  anyway: `build()` removes any pre-existing host first (idempotency), and now builds the widget
  **detached and themes it before inserting into the DOM**, so there's no unstyled/default first
  paint (the white/black flash the screenshot caught). New Playwright asserts a single host across
  repeated config posts + open/close toggles. (2) **Sidebar** (`shell/sidebar*.tsx`): the `<nav>`
  flex child lacked `min-h-0`, and the `aside` was `lg:static` under a `min-h-screen` shell, so it
  grew past the viewport and pushed the footer (Scale plan card + Collapse button) below the fold.
  Fix: `min-h-0` on the scrolling `<nav>` **and** `lg:sticky lg:top-0 lg:h-screen` on the aside to
  bound it to the viewport. Added a **header collapse toggle** beside the logo (rendered in both
  expanded + collapsed states, same `toggleCollapsed` as the footer control). Playwright: footer
  visible without scrolling at a short viewport; header toggle collapses/expands.

## Roadmap / deferred enhancements
List any provider/channel/billing key that is stubbed and needs a real value. (See `ENV.md`.)

## Roadmap / deferred enhancements
- ✅ ~~**Realtime hub → Redis pub/sub.**~~ **DONE (Phase 20, ADR-028).** The hub bridges over Redis
  behind the same `subscribe`/`unsubscribe`/`publish` interface; cross-node delivery is tested.
- ✅ ~~**Webhook retry sweep.**~~ **DONE (Phase 20).** `webhooks.sweep_pending` Celery beat job
  re-enqueues `pending` deliveries past `next_retry_at`; a `beat` service runs it.
- **`provision-client.mjs` doesn't tag the workflows it clones.** The script predates ADR-040 by a
  few hours, so every client it provisions gets an **untagged** workflow — visible to every org
  under the permissive default until someone tags it by hand, which is precisely the state the
  tagging rule exists to end. The org slug is already in scope at clone time (it's what builds the
  webhook path), so the fix is to set the tag in the same `POST /api/v1/workflows` call, plus
  `internal` on the template itself. Until then, provisioning quietly grows the tagging backlog.
- **Consider deny-by-default for n8n visibility** (ADR-040 follow-up): once most workflows carry
  tags, flip the untagged default from visible-to-all to visible-to-none, or replace tags with a
  BotForge-side `workflow_id → org_id` mapping table that doesn't depend on the operator
  remembering. Worth doing before ~20 clients share one n8n.
- **`docker-compose.prod.yml` has no `n8n` service.** It passes `N8N_BASE_URL: http://n8n:5678`
  to api/worker, but nothing in that file defines an `n8n` host, so every n8n feature (tools,
  automations, `scripts/provision-client.mjs` step 5) fails against a prod stack unless an
  external instance is supplied. Fix: add the service, internal-only with no published port,
  plus a volume for `/home/node/.n8n` and `N8N_DIAGNOSTICS_ENABLED=false` (see the dev service).
- **The rate limiter has no timeout on its Redis probe.** Measured 2026-07-30 while verifying the
  email work: with Redis unreachable, a signup takes **~4.3s** before `ratelimit_redis_unavailable`
  fires and the in-memory fallback takes over — per request, on every rate-limited endpoint (auth,
  public chat, channel webhooks). The fallback is correct, it's just reached slowly. Fix: a short
  connect/op timeout on the limiter's Redis client, or a cached "Redis is down" flag with a
  re-probe interval so only the first request pays. Unrelated to email; email's own enqueue is
  already bounded.
- **Async n8n late-result re-injection** (from ADR-025): async n8n tools resolve the `tool_run`
  record via the signed callback, but a late result is not re-injected into the same generation
  turn. Options: a "pending → notify" follow-up message on the conversation, or a short bounded
  wait on the callback before the turn ends. Deferred; the callback + record resolution work.
- **The E2E suite has outgrown the hardcoded public rate limits.** At 41 specs, a full
  back-to-back `playwright test` run intermittently trips `public_chat` (60/min) and
  `channel_webhook` (120/min) — 19 `429`s in one observed run — so a handful of specs fail and
  pass again in isolation. `AUTH_RATE_LIMIT` is already env-tunable for exactly this reason;
  these two are not. Fix: make their limits settings-driven and lift them in the E2E env,
  rather than raising them in production defaults.
- **Dashboard `AgentsPanel` / `ConversationsPanel` still render mock data.** `dashboard/page.tsx`
  passes `agents` and `recentConversations` from `@/lib/mock/data` into those two panels, so a
  fresh org sees invented agents ("Support Concierge", 1.3K chats) and invented conversations
  next to its own real stat cards, usage chart, and channel breakdown — which *are* wired to the
  live API. Noticed while adding the per-channel breakdown (2026-07-28) and deliberately left
  alone rather than silently widening that change. Fix: swap in `listAgents()` and the real
  conversations/inbox list the way `DashboardStats` already does.
- **Analytics page has no date-range or per-agent filter UI.** Every query on
  `analytics/page.tsx` calls the API with zero params, so the page always shows the backend's
  default last-30-days across all agents — even though `overview`/`usage`/`latency`/`export` all
  accept `agent_id`, `from`, `to`, and now `channel`. The controls were never built. Adding an
  agent picker + range picker would light up filtering across every view at once, including the
  new channel breakdown.
- ✅ ~~**httpOnly cookie migration for web auth tokens (ADR-019).**~~ **Refresh token DONE (Phase
  20)** — moved to an httpOnly/Secure/SameSite cookie set by a Next BFF (`/api/auth/*`). The
  **access token remains JS-readable by architectural necessity** (cross-origin Bearer + SSE + the
  inbox WebSocket's `?token=` query param). Documented in `docs/SECURITY.md §1`.
- ~~**Next.js 14 → 16 major upgrade (clears 5 web advisories).**~~ **DONE (Phase 19).** Upgraded to
  Next 16.2 + React 19.2 + ESLint 9 flat config; migrated async route params, `middleware.ts`→`proxy.ts`,
  and `next lint`→ESLint CLI; pinned `postcss ^8.5.10` to clear the nested-next copy. `npm audit` now
  reports **0 vulnerabilities** (was 4 high + 1 moderate). tsc + eslint + build + the full Playwright
  suite are green.
- **Drop `python-jose` → `PyJWT`/`authlib`** to clear the transitive `ecdsa` advisory (PYSEC-2026-1325,
  no fix). Not exploitable today (JWTs are HS256 symmetric; no ECDSA ops). See `docs/SECURITY.md §8`.

## Out of scope for v1
Full visual flow builder (ship minimal first), voice/telephony, native mobile apps, bot
marketplace, SSO/SAML, fine-tuning UI, MCP tool bridge, Qdrant swap, Kubernetes/Helm.
