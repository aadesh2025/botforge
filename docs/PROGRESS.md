# PROGRESS.md — Build Progress & Roadmap

Claude Code updates this after every phase (per `CLAUDE.md §9`): what shipped, what's
stubbed/deferred, and any gaps waiting on human secrets.

## Status by phase
| Phase | Title | Status | Notes |
|---|---|---|---|
| 0 | Repo/tooling/CI/compose | ✅ | git, web + api scaffolds, docker-compose (postgres+pgvector/redis/api/worker/web/n8n/ollama), .env.example, Makefile, CI. **Verified: `docker compose up postgres redis` healthy, `/readyz` green (db+redis reachable).** Remaining: on-start alembic in api container (later), Playwright in CI (Phase 19). |
| 1 | Database foundation | ✅ | All 27 models, UUIDv7 base + mixins, org-scoped repository (cross-org isolation test), Alembic async. **Verified against real Postgres: `alembic upgrade head` created all 27 tables + pgcrypto/vector extensions + `chunks.embedding vector(768)`; seed ran (idempotent); 10 tests + ruff + mypy green.** |
| 2 | Auth & accounts | ✅ | Backend (argon2/JWT+rotating refresh/verify/reset/magic-link/OAuth/sessions/rate-limit). **2.6 web auth done: login+signup pages + cookie token store + route-guard middleware + AuthGate (/me+orgs bootstrap, create-first-org). Verified live: signup→org→dashboard, login→dashboard.** Tagged phase-02-complete. |
| 3 | Orgs/RBAC | 🟨 mostly done | Backend complete (CRUD/members/invites/transfer/RBAC/audit, 37 tests). **3.4 partial: org switcher wired to real /v1/orgs (list/switch/create), verified live. Remaining: members/invitations settings UI + RoleGuard still on mocks.** |
| 4 | App shell & design system | ✅ | Design tokens, dark-first ember system, full app shell + dashboard. **4.3 done: typed API client (`lib/api`, hand-written) with Bearer+X-Org-Id+401-refresh + SSE reader; real `/me` renders in shell.** Tagged phase-04-complete. |
| 5 | LLM provider layer | ✅ | app/llm: ChatProvider/EmbeddingProvider protocols, Fake providers, OpenAICompatible base + Groq/Ollama/OpenRouter/OpenAI/custom (chat+stream+models), Gemini + Anthropic adapters (native translation), PRICING + cost, provider resolution (agent→org→env) w/ Fernet-decrypted keys, fallback chain. /v1/credentials CRUD (masked) + test + /providers catalog. 54 tests pass (mock HTTP transport, no live keys needed); ruff+mypy clean. Tagged phase-05-complete. |
| 6 | Agents & versions | ✅ | Backend (CRUD/duplicate/versions/publish/rollback/playground stream). **6.4 done: agents list + builder wired to real API — loads real agent+version, debounced autosave (PATCH), publish, and real SSE playground streaming. Verified live: create→configure→autosave persists→publish→playground streams (echo fallback + graceful provider-error surfacing).** 61 tests pass; ruff+mypy clean. Tagged phase-06-complete. |
| 7 | Knowledge base & RAG | 🟨 UI only | Knowledge list + detail (upload zones, documents table with live status/progress). Ingestion/RAG backend pending. |
| 8 | Chat persistence & memory | ⬜ | |
| 9 | Tools & tool calling | ⬜ | UI surfaces in builder Tools tab (mock) |
| 10 | n8n integration | 🟨 UI only | Automations page (workflow list, bind-as-tool) against mocks; real n8n client pending. |
| 11 | Web widget | 🟨 UI only | Live widget preview in builder Channels tab; actual embeddable widget SDK pending. |
| 12 | Messaging channels | 🟨 UI only | Channels connect UI (mock); channel backends pending. |
| 13 | Inbox & handoff | 🟨 UI only | Two-pane inbox: list/filters, thread, takeover/handback/assign/tags (mock). Real-time WS pending. |
| 14 | Analytics & metering | 🟨 UI only | Analytics dashboards (stat cards, activity chart, channel/latency bars, top/unanswered) against mocks. |
| 15 | API keys/webhooks/audit | 🟨 UI only | Settings pages: API keys, webhooks, provider credentials, org members, profile (mock). |
| 16 | Guardrails & hardening | ⬜ | |
| 17 | Admin console | ⬜ | |
| 18 | Billing (optional) | ⬜ | |
| 19 | E2E/docs/polish | ⬜ | |
| 20 | Production deployment | ⬜ | |

Legend: ⬜ not started · 🟨 in progress · ✅ complete · ⏸️ deferred

## Waiting on human (missing secrets)
List any provider/channel/billing key that is stubbed and needs a real value. (See `ENV.md`.)

## Roadmap / out of scope for v1
Full visual flow builder (ship minimal first), voice/telephony, native mobile apps, bot
marketplace, SSO/SAML, fine-tuning UI, MCP tool bridge, Qdrant swap, Kubernetes/Helm.
