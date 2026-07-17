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
