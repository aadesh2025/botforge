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
