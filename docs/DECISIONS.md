# DECISIONS.md — Architecture Decision Log (ADR)

Claude Code appends an entry here whenever it makes a non-obvious choice (per `CLAUDE.md §1`).
Format each entry as below. Newest at the top.

---

## Template
### ADR-000: <title>
- **Date:** YYYY-MM-DD
- **Status:** proposed | accepted | superseded by ADR-XXX
- **Context:** what forced the decision.
- **Decision:** what was chosen.
- **Alternatives considered:** options + why rejected.
- **Consequences:** trade-offs, follow-ups.

---

## Build decisions

### ADR-019: Frontend↔backend integration — cookie tokens, hand-written client, SSE reader
- **Date:** 2026-07-17
- **Status:** accepted
- **Context:** Wire the existing mock UI to the real API (closes 2.6/3.4/4.3/6.4). Backend is a
  separate FastAPI on :8000 using Bearer JWT + `X-Org-Id`.
- **Decision:** Tokens in **non-httpOnly cookies** (readable by the SPA + the route-guard
  middleware); a Next `middleware.ts` gates `/dashboard,/agents,…`. API client is
  **hand-written** (`lib/api`), not openapi-generated yet — attaches Bearer + `X-Org-Id`,
  refreshes once on 401, and exposes an **`apiStream` SSE reader** for the playground.
  `AuthGate` bootstraps `/me` + orgs and shows a create-first-org prompt for fresh signups.
  Only backends that exist are wired (auth/orgs/credentials/agents+playground); knowledge/
  inbox/analytics/automations/channels/tools stay on mocks until their phases land. Dev CORS
  uses an `http://localhost:\d+` regex so any web dev port works.
- **Note (prod hardening):** move tokens to httpOnly cookies set by a Next route handler
  before shipping (docs/05 §1).
- **Verified live (Playwright):** signup→create-org→dashboard, login, agent create, builder
  autosave persisting across reload, publish, and SSE playground streaming.

### ADR-030: API keys, outbound webhooks, audit, and frontend RBAC
- **Date:** 2026-07-19
- **Status:** accepted
- **Context:** Phase 15 — programmatic access, event delivery, audit trail, and closing the
  Phase 3 RBAC-UI gap.
- **Decisions:**
  - **API keys act as their creator.** A `bf_`-prefixed key is stored as `sha256` + a prefix for
    O(1) lookup; `current_org` accepts it via `X-API-Key` or `Bearer bf_…`, resolves the key's
    org, and builds an `OrgContext` whose acting user is the key's creator — so `created_by`,
    audit, and RBAC all reuse the creator's membership role. Scopes are stored (and exposed on
    `OrgContext.scopes`) for future fine-grained checks; enforcement is currently role-based.
  - **Webhooks: emit → persist → deliver.** `emit_event` (best-effort, never raises into the
    request) creates a `WebhookDelivery` per subscribed endpoint and enqueues a Celery delivery
    task. `deliver_delivery` signs (`HMAC-SHA256` of `"{ts}.{body}"`), POSTs, and records
    status/attempts/response; failures set `pending` + `next_retry_at` (exp backoff, cap 5
    attempts) and Celery retries. **Webhook URLs are SSRF-guarded** (arbitrary user input), unlike
    the trusted n8n base URL. The full event catalog is emitted from the runtime (message,
    conversation, handoff, document, tool, usage.threshold).
  - **Shared audit writer** (`app/core/audit.write_audit`) records sensitive mutations across
    modules (org, member, apikey, webhook); the read API is admin/owner-only (`members:manage`).
  - **Frontend RBAC mirrors the backend matrix** in `lib/rbac` (`useCan`) to hide/disable UI a
    role can't use — the server stays authoritative. Verified live: a viewer sees read-only
    settings and gets 403 from the API on admin actions.

### ADR-029: Analytics computed live from messages; usage_records for metering/quotas
- **Date:** 2026-07-18
- **Status:** accepted
- **Context:** Phase 14 — analytics + usage metering.
- **Decisions:**
  - **Analytics endpoints aggregate live** from `messages`/`conversations`/`handoffs` per request
    (org-scoped, date-ranged), so the numbers are always exactly what's in the tables — no
    dependence on a rollup having run. Verified by matching a direct `messages` SQL aggregate.
  - **`usage_records` + `quotas` are a separate metering layer** populated by a Celery rollup
    (`app/worker/rollup`) — a daily per-(agent, provider, model) upsert used for quota
    enforcement + a `usage.threshold` event (emitted as a webhook in Phase 15). The rollup's
    totals match the live message sums.
  - **Metric definitions:** resolution_rate = 1 − (conversations with a `Handoff` / total
    conversations); "unanswered/escalated" = user questions in conversations that got a handoff
    (a pragmatic proxy — a dedicated "no-citation" marker can refine it later); latency from
    `messages.latency_ms` via Postgres `percentile_cont`. Free providers cost 0 (`PRICING`), so
    real cost is genuinely $0 until a paid provider is used.
  - **Keyword handoff is an inbound (widget/channel) behaviour** — the authenticated dashboard
    `/chat` doesn't run it (it's an operator/test surface), so analytics escalations come from
    end-user surfaces.

### ADR-028: Human handoff + inbox with an in-process realtime hub
- **Date:** 2026-07-18
- **Status:** accepted
- **Context:** Phase 13 — pause the bot for a human, queue it in an inbox, deliver operator
  replies back to the end user in real time.
- **Decisions:**
  - **Handoff = `conversation.status="handoff"` + a `Handoff` row.** `app/chat/handoff` triggers
    it from a keyword (when `features.handoff_enabled`) or the `request_handoff` built-in tool.
    The shared `InboundTurn` (ADR-027) already checks the status and stays silent while paused —
    so every surface (widget + channels) pauses consistently. Handback flips the status back to
    `active` and the bot resumes.
  - **Realtime via a tiny in-process pub/sub** (`app/realtime/hub`): topics `inbox:{org}` and
    `conv:{id}`. The operator inbox WS subscribes to the org topic (handoff/message events); the
    **widget** opens a listen-only socket (`/v1/public/agents/{key}/subscribe`) to its
    conversation topic and appends operator replies + handback pushes live. Single-process only;
    swap the hub body for Redis pub/sub to scale out (same interface).
  - **Operator replies** persist as `role="assistant", provider="operator"` (distinct from bot
    turns), deliver to the end user's channel via the adapter (`send`) for messaging channels and
    via the hub push for the widget, and emit an inbox event.
  - **Inbox queue = conversations that have a `Handoff` record** (any status), filterable by the
    conversation's current status — so resolved handoffs stay visible for history.

### ADR-027: Messaging channels via a shared inbound turn + adapter registry
- **Date:** 2026-07-18
- **Status:** accepted
- **Context:** Phase 12 — Telegram/WhatsApp/Slack/Discord, keeping the runtime channel-agnostic.
- **Decisions:**
  - **One shared inbound turn.** `app/chat/inbound.InboundTurn` factors "persist the user
    message → (unless handed off) run the bot → persist the assistant reply" out of the public
    widget service. The widget streams its events; channels call `.run()` and forward
    `result.content`. This is also where the **handoff pause** lives (a `status="handoff"`
    conversation persists the inbound message but the bot stays silent — Phase 13).
  - **A thin `BaseChannel` adapter per platform** (`verify` / `parse_inbound` / `send` /
    `on_enable`) on a registry. The channel service handles CRUD + inbound orchestration; each
    adapter only knows its provider's signature scheme and message shape.
  - **Signature verification is mandatory per platform**: Telegram secret-token header, WhatsApp
    `X-Hub-Signature-256` (+ GET verify challenge), Slack v0 HMAC (+ timestamp replay window +
    `url_verification`), Discord Ed25519 over `timestamp+body` (+ PING/PONG). Discord replies
    inline in the interaction response (no async `send`).
  - **Tokens encrypted at rest** (Fernet, same as provider creds) and **masked** (`••••set`) in
    API responses; the per-channel `webhook_secret` authenticates Telegram callbacks.
  - **Per-channel config, not global env.** Tokens live on the `Channel` row so one org can run
    several bots; `TELEGRAM_BOT_TOKEN` etc. are entered in the Channels tab. Dropping a real
    token in + exposing a public webhook URL is the only step to go live.
  - **Local verifiability:** providers push to a public URL and we can't reach their hosts from
    dev, so provider *delivery* is mock-tested; inbound → real-bot → persist is verified live by
    POSTing signed provider-shaped payloads to the running API.

### ADR-026: Public widget surface + a zero-dependency Shadow-DOM widget
- **Date:** 2026-07-18
- **Status:** accepted
- **Context:** Phase 11 — an embeddable web widget that chats without dashboard auth.
- **Decisions:**
  - **Reuse the dashboard runtime.** `build_tooling`, `_resolve_provider`, `_maybe_summarize`,
    and `_finalize_turn` were refactored to take `org_id`/`Conversation` instead of an
    `OrgContext`, so the public chat (`app/modules/public`) resolves the agent+org from its
    `public_key` and runs the exact same assembly → retrieval → tools → `run_turn` → persistence
    path. Widget conversations use `channel="widget"` and show up in the dashboard's conversations
    browser (same org).
  - **Widget appearance lives in `agent_version.persona.widget`** (color/position/launcher/mode/
    branding) — so it round-trips through the builder's existing version autosave with no schema
    change; the public `/config` endpoint reads it.
  - **The widget is one dependency-free `widget.js`** rendered into a **Shadow DOM** (full style
    isolation), streaming over the public SSE endpoint (works cross-origin from any host). It
    ships its own minimal, escape-first markdown renderer (no library) and exposes
    `window.BotForge` (open/close/toggle/sendMessage/on/setUser). Built via a trivial
    `node build.mjs` (esbuild-minified if present, else plain copy) into `apps/web/public/` so the
    web app serves it at `/widget.js`.
  - **Rate limiting:** public chat is throttled per client IP (60/min) via the shared limiter.

### ADR-025: n8n integration via the existing tool system
- **Date:** 2026-07-18
- **Status:** accepted
- **Context:** Phase 10 — agents trigger local n8n workflows.
- **Decisions:**
  - **No new runtime path.** An n8n workflow becomes a `Tool` row with `type="n8n"` and
    `config={workflow_id, workflow_name, webhook_url, mode}`. The Phase-9 tool loop already
    calls it; only a `type=="n8n"` branch in `_dispatch` + an `execute_n8n_tool` were added
    (ADR-024 paying off).
  - **Signing:** outbound webhooks carry `X-BotForge-Signature` = HMAC-SHA256 of
    `"{timestamp}.{body}"` with `N8N_WEBHOOK_SIGNING_SECRET`; the callback endpoint verifies the
    same (constant-time) with ±300s replay protection.
  - **n8n calls are NOT SSRF-guarded** — the target is the operator-configured, trusted
    `N8N_BASE_URL` (loopback in dev), unlike user-supplied HTTP-tool URLs which are guarded.
  - **Async without blocking the turn:** the ToolRun is created (`pending`) *before* dispatch so
    its id is the callback token; async n8n returns an "accepted" result immediately and the
    signed `POST /v1/tools/n8n/callback` later resolves the pending run. In-turn re-injection of
    a late async result is a future enhancement.
  - **Discovery** uses n8n's public REST API (`X-N8N-API-KEY`); the webhook URL is extracted from
    the workflow's Webhook node. If `N8N_API_KEY` is unset, listing/binding fails loudly (503)
    but the rest of the app keeps working (CLAUDE §7).

### ADR-024: Tools as rows, a decoupled executor, and an iteration-capped loop
- **Date:** 2026-07-18
- **Status:** accepted
- **Context:** Phase 9 — built-in + user-defined tools the agent can call mid-conversation.
- **Decisions:**
  - **Every enabled tool is a `Tool` row** (`type=builtin|http`, scoped to an agent). Enabling a
    built-in creates a row (its `input_schema` mirrors the canonical schema); this keeps
    `tool_runs.tool_id` a real FK for both built-ins and HTTP tools. The runtime loads an agent's
    enabled rows → `ToolSpec`s for the provider.
  - **The runtime stays decoupled from the tools package.** `tools.service.build_tooling` returns
    `(specs, executor)` where `executor(call)` runs the tool, logs a `ToolRun`, and returns a plain
    dict `{output, status, error}`. `chat.runtime.run_turn` takes that callable and knows nothing
    about the tools module — avoiding an import cycle (conversations/agents → tools → llm/rag).
  - **`run_turn` is the single loop** used by both the persisted chat and the playground: stream a
    provider pass, and if the model emits tool calls (and budget remains), append an assistant
    tool-call message + `tool` result messages and re-run — capped by `TOOL_MAX_ITERATIONS`. It
    emits `tool_call`/`tool_result` events and one aggregated `done`.
  - **Safety:** `calculator` uses an AST allow-list (no `eval`); `http_request` and HTTP tools
    reuse the SSRF host check (reject private/loopback) and a per-tool timeout; a tool exception
    never crashes the turn (logged as an error `ToolRun`).
  - **Rate-limit fix (found via the growing suite):** `rate_limit` now resolves limit/window
    per-request instead of at import time, so runtime overrides (tests raising the limit) apply.

### ADR-023: Branch-on-edit for published agent versions
- **Date:** 2026-07-18
- **Status:** accepted
- **Context:** The builder autosaves via `PATCH /agents/{id}/versions/{n}`, but a published
  version is immutable (previously returned 409), which the autosave swallowed → edits to a
  live agent were silently lost.
- **Decision:** `update_version` now forks on edit: if the targeted version is published, it
  transparently creates a new draft copied from the latest version (per ADR-018) and applies
  the patch to that. The response carries the new (higher) version number; the builder detects
  the bump, re-targets its autosave at the new draft, and shows an "Editing new draft vN" badge.
- **Consequences:** No silent failures; editing a live agent always produces an editable draft
  you then publish. The old 409 path is gone.

### ADR-022: Chat runtime, persistence, and memory
- **Date:** 2026-07-18
- **Status:** accepted
- **Context:** Phase 8 — durable dashboard chat with memory, separate from the ephemeral
  builder playground.
- **Decisions:**
  - **Shared runtime in `app/chat`.** `assembly.build_messages` orders the prompt per docs/06
    §2 (system → retrieved context → memory summary → recent window → current turn).
    `runtime.stream_turn` runs one provider pass, forwards `StreamEvent`s, and accumulates a
    `TurnResult` (content/usage/cost/citations) the caller persists. Phase 9 wraps this with a
    tool loop.
  - **Persistence lives in the conversations service**, which owns `POST /v1/agents/{id}/chat`
    (SSE + non-stream) and the conversation CRUD. The request-scoped session is used inside the
    `StreamingResponse` generator (Starlette consumes it before the `get_session` commit), and
    the WS handler uses its own committing `SessionFactory` session per socket.
  - **The "live" version answers**: `current_version_id` if published, else the latest draft
    (the playground still uses the latest draft). The builder playground stays ephemeral; the
    persisted `/chat` endpoint backs the conversations browser.
  - **Memory:** a recent window (`MEMORY_WINDOW_MESSAGES`) stays verbatim; once a conversation
    passes `MEMORY_SUMMARY_THRESHOLD`, newly aged-out turns are folded into
    `conversation.memory_summary` via a **separate small model** (`SUMMARY_PROVIDER`/`MODEL`,
    groq default → fake fallback) — never the agent's own model, so a heavy local model like
    qwen3:14b is never pulled into background summaries. `meta.summarized_upto` bounds the work
    to only the newly aged slice each turn.
  - **WebSocket** `WS /v1/agents/{id}/chat/ws` mirrors the SSE contract; auth is via
    `?token=&org_id=` query params (browsers can't set WS Authorization headers).

### ADR-021: RAG pipeline shape — char-based chunking, hybrid RRF, fake-embed KBs for tests
- **Date:** 2026-07-18
- **Status:** accepted
- **Context:** Phase 7 knowledge base & RAG.
- **Decisions:**
  - **Ingestion is a plain async function** (`app/rag/ingest.ingest_document`) that the Celery
    task (`app/worker/tasks`) wraps with its own committing session. This keeps the whole
    pipeline directly testable against the transaction-rolled-back test session (call it
    inline) without a broker, exactly mirroring how playground tests inject a fake provider.
  - **`chunk_size`/`chunk_overlap` are interpreted in characters** (not tokens). The spec cited
    "~800 tokens/100 overlap" but the KB model ships `1000/150`; treating those as characters is
    predictable, tokenizer-free, and good enough for retrieval. `token_count` uses a ~4-chars/token
    estimate to avoid a heavy tokenizer dependency.
  - **Retrieval = pgvector cosine top-k, optional hybrid** merging a Postgres full-text
    (`ts_rank`) list via reciprocal rank fusion (k=60). `score_threshold` filters vector
    candidates; lexical (FTS) hits bypass it, so hybrid still surfaces exact-term matches whose
    vector similarity is below threshold (their displayed `score` is the vector similarity, 0.0
    when they were an FTS-only hit). Note: `plainto_tsquery` ANDs terms, so a query only
    lexically matches when *all* its non-stopword tokens appear in a chunk.
  - **Embedding provider per KB**, resolved by `build_embedding_provider(kb.embedding_provider,
    …)`. `"fake"` returns a deterministic `FakeEmbeddingProvider(dim=768)` matching the
    `chunks.embedding vector(768)` column, so DB-backed ingestion/retrieval/RAG tests need no
    Ollama/network. Real KBs default to Ollama `nomic-embed-text` (dim 768).
  - **Indexes** added in migration `0004`: HNSW `vector_cosine_ops` on `chunks.embedding` and a
    GIN index on `to_tsvector('english', content)`.
  - **Citations over the wire:** `StreamEvent` gained a `citations` field + a `"citations"`
    event type (plain dicts, so the LLM layer stays independent of the RAG package); the
    playground emits one `citations` event before the provider stream and includes citations in
    the non-streaming response.

### ADR-020: Two streaming/credential bugs found via the live integration test
- **Date:** 2026-07-17
- **Status:** accepted
- **Fixes:** (1) `OpenAICompatibleProvider.stream` called `resp.text` on an *unread* streaming
  response → `httpx.ResponseNotRead` (not a `ProviderError`, so uncaught → empty stream + crash).
  Now `await resp.aread()` before reading the error body. (2) `registry.resolve_credential`
  treated whitespace-only env keys (from `.env.example` comment alignment) as real keys →
  spurious provider calls. Now blank/whitespace env values are treated as unset (fall back to
  the fake provider). Both surfaced only because the wired UI exercised the real streaming path.

### ADR-018: Agent versioning, model_config aliasing, and Python-side timestamps
- **Date:** 2026-07-17
- **Status:** accepted
- **Context:** Phase 6 agents + the first endpoint that streams through the LLM layer.
- **Decision:** Latest `agent_version` = the editable draft; publishing sets `is_published`,
  flips `agent.status` to published, and points `current_version_id` at it; published versions
  are immutable (edits require a new draft copied from the latest); rollback re-points current
  at an older published version. The JSON key `model_config` is Pydantic-reserved, so schemas
  use field `llm_config` with `alias="model_config"` (FastAPI serializes by alias). Playground
  builds a `ChatRequest` from the draft's model_config and streams via `get_chat_provider` +
  the `StreamEvent` SSE contract; when no key is configured it falls back to `FakeChatProvider`
  so the build isn't blocked (CLAUDE §7). Playground route sets `response_model=None`
  (StreamingResponse | dict union).
- **Gotcha fixed:** server-side `onupdate=func.now()` on `updated_at` expired the attribute
  after UPDATE, causing async lazy-load (`MissingGreenlet`) when serializing the response.
  Switched `TimestampMixin.updated_at` to **Python-side** default/onupdate so the value is set
  on the instance at flush time. Applies to every timestamped model.

### ADR-017: LLM layer — one OpenAI-compatible base, transport-injectable for tests
- **Date:** 2026-07-17
- **Status:** accepted
- **Context:** Phase 5 provider layer. Most providers (Groq/Ollama/OpenRouter/OpenAI/custom)
  speak the OpenAI protocol; Gemini + Anthropic don't. Need to test without live keys.
- **Decision:** One `OpenAICompatibleProvider` parameterized by `base_url`+key with thin
  subclasses; dedicated `gemini.py`/`anthropic.py` adapters with pure `to_*_payload()`
  translation functions (unit-tested). Every provider accepts an optional
  `httpx.AsyncBaseTransport` so tests drive them with `httpx.MockTransport` — no network, no
  keys. Streaming uses the `StreamEvent` contract (token/tool_call/done); Gemini/Anthropic
  derive a token stream from the full response for now. Key resolution order: agent credential
  → org default → env (`registry.resolve_credential`, Fernet-decrypted). `run_with_fallback`
  tries providers in order on `ProviderError`. `PRICING` in micros/1K tokens (free providers=0).
- **Consequences:** `/v1/credentials` manages BYO keys (masked, never returned in full); the
  chat runtime (Phase 6/8) calls `get_chat_provider` + `run_with_fallback`. Phase 5 fully
  backend → tagged phase-05-complete.

### ADR-016: RBAC as a central permission matrix; org context via path + X-Org-Id
- **Date:** 2026-07-17
- **Status:** accepted
- **Context:** Phase 3 tenancy/RBAC. Need consistent authorization reusable by every later
  module, and a single way to resolve "the current org."
- **Decision:** `core/rbac.py` holds capability constants + a `ROLE_PERMISSIONS` matrix
  (docs/02 §6); services call `require_permission(role, perm)` → `403 org.forbidden`. Org
  resolution has two dependencies: `org_context` (from the `{org_id}` path, for /v1/orgs
  routes) and `current_org` (from the `X-Org-Id` header, for org-scoped resource routes in
  later phases) — both verify active membership. Owner is assigned only via
  transfer-ownership (role-change endpoints reject "owner"); removing a member is a soft
  status flip to "removed" (keeps the unique (org,user) row for re-invite). Sensitive
  mutations write `audit_logs`.
- **Consequences:** later modules (agents, KB, tools, channels, inbox, apikeys) depend on
  `current_org` + `require_permission`; the frontend org switcher (3.4) is deferred.

### ADR-015: Auth design — opaque rotating refresh tokens, module layout, DB-backed tests
- **Date:** 2026-07-17
- **Status:** accepted
- **Context:** Phase 2 auth. Need secure sessions, testability without a mail server, and a
  clean module structure per `02 §2`.
- **Decision:** Access = short-lived **JWT** (15m, HS256). Refresh = **opaque** random token,
  only its SHA-256 hash stored in `sessions`; refresh **rotates** (old row revoked) — enables
  server-side revocation and logout. Argon2 for passwords; **Fernet** (SECRET_KEY-derived) for
  secrets at rest (OAuth tokens). Added an **`email_verification_tokens`** table (not in the
  original `03` schema) mirroring the reset-token pattern. Email via a **console backend** with
  an in-memory outbox tests read to extract tokens. OAuth uses PKCE(Google)+state held in a
  process-local store; unconfigured providers return `501 auth.oauth_not_configured`. Rate
  limiting via Redis fixed-window with an **in-memory fallback** so it works without Redis.
  Auth code lives in `app/modules/auth/{schemas,deps,service,oauth,router}.py`.
- **Testing:** DB-backed tests run against real Postgres inside a **transaction rolled back**
  per test (`conftest` overrides `get_session`); CI runs pgvector + redis services + migrations.
- **Consequences:** stable error codes (`auth.*`); `/me` returns memberships (empty until
  Phase 3). Frontend auth pages (2.6) deferred to a later frontend pass.

### ADR-014: UUIDv7 primary keys; String enums; JSONB config; autogenerate migrations
- **Date:** 2026-07-17
- **Status:** accepted
- **Context:** Phase 1 schema. Python stdlib has no uuid7; PG16 has no native gen; we want
  time-ordered keys for index locality without a new dependency.
- **Decision:** Generate **UUIDv7** in Python (RFC 9562 layout: 48-bit ms + random). Enum-like
  columns are **String** (portable; app/CHECK-enforced) rather than PG ENUM types (avoids
  fragile enum migrations). Flexible config (persona, model_config, rag_config, tool config,
  channel config, citations) is **JSONB**. The initial migration only enables `pgcrypto` +
  `vector`; the table DDL is **autogenerated** from the models once Postgres is available
  (models are the source of truth — hand-writing 27 tables invites drift). Tenant isolation is
  enforced in a **repository base** that filters every query by `organization_id`.
- **Consequences:** `alembic upgrade head`, the tables migration, and `make seed` are verified
  when the Docker stack is up; models/repository/uuid7 are already unit-tested without a DB.

### ADR-013: uv + hatchling for the Python backend; structlog for logging
- **Date:** 2026-07-17
- **Status:** accepted
- **Context:** Backend Phase 0 scaffold. Local machine has uv 0.11 (no poetry); need fast,
  reproducible installs and a lockfile.
- **Decision:** Manage `apps/api` with **uv** (`uv sync`, `uv.lock` committed) and hatchling as
  build backend. Structured JSON logging via **structlog** (pretty console in dev, JSON in
  prod). Typed error envelope `{error:{code,message,details}}` via FastAPI exception handlers;
  request-id middleware binds a per-request id to the log context. `/readyz` probes Postgres +
  Redis and 503s until both are reachable, never crashing.
- **Consequences:** Dockerfile uses the `ghcr.io/astral-sh/uv` image; CI uses `astral-sh/setup-uv`.
  Alembic on-start migration deferred to Phase 1 (compose `command` has a TODO marker).

### ADR-010: Dark-first "forge" design system (ember accent over graphite)
- **Date:** 2026-07-17
- **Status:** accepted
- **Context:** The frontend spec (`05`) is functional, not visual — it defines screens/data
  but no identity. User asked for a clean, premium SaaS dashboard in a Linear/Vercel dark-first
  direction. That direction is also one of the common AI-default looks, so it needed a
  differentiator.
- **Decision:** Cool graphite surfaces (`#0A0B0D`/`#131519`) with hairline borders and a tight
  grid, spending the one aesthetic risk on a signature **ember** accent (`#FF6A3D` → gold
  `#FFB020`) that the brand name "BotForge" earns. Typography: Space Grotesk (display) + Inter
  (body) + JetBrains Mono (data), deliberately not Inter-everywhere. Tokens stored as RGB
  channels in CSS vars so Tailwind opacity modifiers work; `darkMode: "class"` via next-themes,
  dark default with a light override.
- **Alternatives considered:** generic indigo shadcn defaults (rejected: templated); light-first
  Stripe/Notion look (rejected: user chose dark-first).
- **Consequences:** All UI derives color/type from `globals.css` tokens + `tailwind.config.ts`.

### ADR-011: Typed mock layer before the generated API client
- **Date:** 2026-07-17
- **Status:** accepted
- **Context:** Frontend spec generates its API client from the backend `openapi.json`, but the
  backend doesn't exist yet and the user wants the premium dashboard now.
- **Decision:** Build the UI against typed fixtures in `src/lib/mock/*` whose shapes mirror
  `03`/`04`. Swap to the generated client at Phase 5 without changing components.
- **Consequences:** Screens are fully typed today; only the data source changes later.

### ADR-012: Hand-built SVG charts for bespoke widgets, Recharts for standard analytics
- **Date:** 2026-07-17
- **Status:** accepted
- **Context:** Recharts (spec default) looks generic out of the box; the dashboard's hero
  activity chart needed to feel premium.
- **Decision:** A custom, theme-aware SVG area chart (`usage-chart.tsx`) with ember gradient,
  hover crosshair, and a clamped/flipping tooltip for the dashboard. Recharts still planned for
  the fuller `/analytics` dashboards where standard chart types suffice.
- **Consequences:** No chart dep pulled in yet; revisit at Phase 14.

## Pre-recorded decisions (from the spec)
### ADR-001: Modular monolith backend (not microservices)
- **Status:** accepted. **Context:** solo/AI build, must run on one machine.
- **Decision:** one FastAPI app organized by domain modules. **Consequences:** simplest to
  build/deploy; module boundaries allow later extraction.

### ADR-002: Row-scoped multi-tenancy by `organization_id` (+ optional RLS)
- **Status:** accepted. Shared DB/schema with enforced org filtering; RLS as defense-in-depth.

### ADR-003: Groq-first, free-first LLM ordering
- **Status:** accepted. Default Groq; then Gemini free / Ollama / OpenRouter; then OpenAI /
  Anthropic paid; plus custom OpenAI-compatible + BYO keys.

### ADR-004: pgvector as default vector store behind an interface
- **Status:** accepted. Swap to Qdrant later without touching callers.

### ADR-005: OpenAI-compatible provider base class
- **Status:** accepted. One adapter parameterized by base_url/key covers Groq/OpenRouter/
  Ollama/OpenAI/custom; dedicated adapters for Gemini and Anthropic.
