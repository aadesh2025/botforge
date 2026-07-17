# PROGRESS.md — Build Progress & Roadmap

Claude Code updates this after every phase (per `CLAUDE.md §9`): what shipped, what's
stubbed/deferred, and any gaps waiting on human secrets.

## Status by phase
| Phase | Title | Status | Notes |
|---|---|---|---|
| 0 | Repo/tooling/CI/compose | ✅ | git, web + api scaffolds, docker-compose (postgres+pgvector/redis/api/worker/web/n8n/ollama), .env.example, Makefile, CI. **Verified: `docker compose up postgres redis` healthy, `/readyz` green (db+redis reachable).** Remaining: on-start alembic in api container (later), Playwright in CI (Phase 19). |
| 1 | Database foundation | ✅ | All 27 models, UUIDv7 base + mixins, org-scoped repository (cross-org isolation test), Alembic async. **Verified against real Postgres: `alembic upgrade head` created all 27 tables + pgcrypto/vector extensions + `chunks.embedding vector(768)`; seed ran (idempotent); 10 tests + ruff + mypy green.** |
| 2 | Auth & accounts | 🟨 backend done | Password auth (argon2), JWT access + rotating refresh (session table), logout, /me; email verification + password reset + magic-link (console email backend w/ test outbox); OAuth Google/GitHub (PKCE+state, stubbed without keys); sessions list/revoke; Redis rate limiting (in-memory fallback); secrets encrypted at rest (Fernet). **25 tests pass vs real Postgres (tx-rollback isolation); live smoke OK; ruff+mypy clean; CI now runs pg+redis+migrations.** Remaining: 2.6 web auth pages (frontend). |
| 3 | Orgs/RBAC | 🟨 backend done | Org CRUD (unique slug, soft-delete), path `{org_id}` + `X-Org-Id` membership resolution (non-members 403), members list/change-role/remove, invitations (invite→accept via email token, mismatch guard), transfer ownership, RBAC matrix (docs/02 §6) enforced per role, audit_logs on sensitive mutations. **37 tests pass vs real Postgres; live smoke OK; ruff+mypy clean.** Remaining: 3.4 web org switcher/settings (frontend). |
| 4 | App shell & design system | ✅ frontend | Design tokens, dark-first ember system, full app shell, and every dashboard route surface built. Remaining (backend-dependent): generated API client. |
| 5 | LLM provider layer | ✅ | app/llm: ChatProvider/EmbeddingProvider protocols, Fake providers, OpenAICompatible base + Groq/Ollama/OpenRouter/OpenAI/custom (chat+stream+models), Gemini + Anthropic adapters (native translation), PRICING + cost, provider resolution (agent→org→env) w/ Fernet-decrypted keys, fallback chain. /v1/credentials CRUD (masked) + test + /providers catalog. 54 tests pass (mock HTTP transport, no live keys needed); ruff+mypy clean. Tagged phase-05-complete. |
| 6 | Agents & versions | 🟨 backend done | Backend: agent CRUD (unique slug, bf_pub_ public key, soft-delete) + duplicate; version lifecycle (draft → patch persona/model_config/rag/features/prompts → publish → rollback, current_version pointer, published versions immutable); **playground chat endpoint streaming real completions through the Phase 5 LLM layer** (fake-provider fallback when no key, per CLAUDE §7). Frontend builder already exists as mocks. 61 tests pass vs real Postgres; live smoke OK; ruff+mypy clean. Remaining: 6.4 wire web builder to the real API. |
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
