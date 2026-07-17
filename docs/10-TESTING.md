# 10 — Testing Strategy & Quality Gates

## 1. Principles
- Every task ships with tests (Definition of Done, `CLAUDE.md §2`). No task is "done" with a
  red suite. Deterministic tests only — use fakes/mocks for LLMs, embeddings, external APIs.
- Test pyramid: many unit tests, fewer integration tests, a focused set of Playwright E2E for
  the critical user journeys.

## 2. Backend (`apps/api`)
- **Framework**: `pytest` + `pytest-asyncio` + `httpx.AsyncClient` against the ASGI app.
- **DB**: ephemeral Postgres (compose service or testcontainers) with pgvector; migrations
  applied per test session; transaction rollback per test for isolation.
- **Fakes**: `FakeProvider`/`FakeEmbeddingProvider` (`06 §6`); fake email backend; mocked
  HTTP for channel/n8n/provider calls (respx/httpx mock).
- **Coverage targets**: >70% overall; ~90% on `llm/`, `rag/`, `chat/`, RBAC, tenant scoping.
- **Must-cover cases**:
  - Tenant isolation: no query crosses `organization_id`.
  - RBAC matrix: each role allowed/denied correctly.
  - Auth: signup/login/refresh-rotation/logout/reset/magic/oauth-link.
  - LLM fallback chain + cost/token accounting.
  - RAG: chunking, embedding dims, retrieval ranking, citations, token budgeting.
  - Tool loop: execution, iteration cap, tool_runs logging, SSRF guard rejects internal IPs.
  - n8n: signed trigger + callback verification.
  - Channels: signature verification + inbound parse + send (mocked).
  - Webhooks: signed delivery + retry/backoff.
  - Rate limiting returns 429 with Retry-After.

## 3. Frontend (`apps/web`)
- **Unit**: Vitest + Testing Library for components/hooks; mock the API client.
- Cover: builder forms (persona/model validation), streaming chat rendering, RoleGuard,
  status badges, error/empty/loading states, org switcher.

## 4. E2E (Playwright) — the acceptance gates
Run against the full `docker compose` stack (real api/db/redis; LLM via Ollama-local or a
recorded/mock provider so CI needs no paid keys). Journeys (mirror `01 §6`):
1. **Signup → org → agent (Groq/local) → chat** in playground.
2. **Upload PDF → becomes ready → agent answers with citations.**
3. **Embed widget on a static page → chat through it.**
4. **Connect Telegram (mock) → message round-trips.**
5. **Bind an n8n workflow (local n8n) → agent triggers it → result used.**
6. **Invite teammate → role restricts what they see.**
7. **Analytics shows conversation + token usage.**

Capture screenshots/video on failure. These specs must pass in CI before a phase that claims
them is tagged.

## 5. Per-phase gates
Each phase's "Gate" in `08-PHASES.md` must be green before tagging `phase-NN-complete`:
run `make test` (unit+integration) + the relevant Playwright specs. If a gate can't be met
because of a missing human secret, stub it, keep the rest green, and record the gap in
`docs/PROGRESS.md`.

## 6. Non-functional checks
- **Perf** (Phase 16): k6/locust script measuring first-token p50 on Groq (NFR-1) and API
  p95; record results in `docs/PROGRESS.md`.
- **Security**: `docs/SECURITY.md` checklist (SSRF, rate limits, headers/CSP, encrypted keys,
  input/file validation, prompt-injection handling) verified with tests where feasible;
  dependency audit (`pip-audit`, `npm audit`) in CI.
- **A11y** (Phase 19): axe/Playwright accessibility checks on key pages + the widget.

## 7. CI wiring
`ci.yml` runs: lint → typecheck → unit → build → compose-up → E2E → teardown. Any failure
fails the build. Coverage reported as an artifact. See `09 §6`.

## 8. Local commands
`make test` (all), `make test-api`, `make test-web`, `make e2e`, `make lint`, `make typecheck`.
Keep them fast; parallelize where possible.
