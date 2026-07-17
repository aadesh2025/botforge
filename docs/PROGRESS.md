# PROGRESS.md — Build Progress & Roadmap

Claude Code updates this after every phase (per `CLAUDE.md §9`): what shipped, what's
stubbed/deferred, and any gaps waiting on human secrets.

## Status by phase
| Phase | Title | Status | Notes |
|---|---|---|---|
| 0 | Repo/tooling/CI/compose | ✅ | git, web + api scaffolds, docker-compose (postgres+pgvector/redis/api/worker/web/n8n/ollama), .env.example, Makefile, CI. **Verified: `docker compose up postgres redis` healthy, `/readyz` green (db+redis reachable).** Remaining: on-start alembic in api container (later), Playwright in CI (Phase 19). |
| 1 | Database foundation | ✅ | All 27 models, UUIDv7 base + mixins, org-scoped repository (cross-org isolation test), Alembic async. **Verified against real Postgres: `alembic upgrade head` created all 27 tables + pgcrypto/vector extensions + `chunks.embedding vector(768)`; seed ran (idempotent); 10 tests + ruff + mypy green.** |
| 2 | Auth & accounts | ⬜ | |
| 3 | Orgs/RBAC | ⬜ | |
| 4 | App shell & design system | ✅ frontend | Design tokens, dark-first ember system, full app shell, and every dashboard route surface built. Remaining (backend-dependent): generated API client. |
| 5 | LLM provider layer | ⬜ | UI surfaces (provider/model picker, sampling, credentials) built in the builder against mocks; backend pending |
| 6 | Agents & versions | 🟨 in progress | Frontend built: agents list + full tabbed Agent Builder (Persona/Model/Knowledge/Tools/Channels/Versions/Settings), draft store with debounced autosave + unsaved-changes indicator, and a streaming Playground (simulated tokens, citations, tool markers). All against the typed mock layer; backend + real streaming pending. |
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
