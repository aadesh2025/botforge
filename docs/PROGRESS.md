# PROGRESS.md — Build Progress & Roadmap

Claude Code updates this after every phase (per `CLAUDE.md §9`): what shipped, what's
stubbed/deferred, and any gaps waiting on human secrets.

## Status by phase
| Phase | Title | Status | Notes |
|---|---|---|---|
| 0 | Repo/tooling/CI/compose | 🟨 partial | git init + Next.js 14 web scaffold done; api/compose/CI pending |
| 1 | Database foundation | ⬜ | |
| 2 | Auth & accounts | ⬜ | |
| 3 | Orgs/RBAC | ⬜ | |
| 4 | App shell & design system | 🟨 in progress | Design tokens, dark-first ember system, app shell (sidebar/topbar/org-switcher/user-menu/theme), and Dashboard overview built against a typed mock layer. Remaining: full component gallery, generated API client (blocked on backend). |
| 5 | LLM provider layer | ⬜ | UI surfaces (provider/model picker, sampling, credentials) built in the builder against mocks; backend pending |
| 6 | Agents & versions | 🟨 in progress | Frontend built: agents list + full tabbed Agent Builder (Persona/Model/Knowledge/Tools/Channels/Versions/Settings), draft store with debounced autosave + unsaved-changes indicator, and a streaming Playground (simulated tokens, citations, tool markers). All against the typed mock layer; backend + real streaming pending. |
| 7 | Knowledge base & RAG | ⬜ | |
| 8 | Chat persistence & memory | ⬜ | |
| 9 | Tools & tool calling | ⬜ | |
| 10 | n8n integration | ⬜ | |
| 11 | Web widget | ⬜ | |
| 12 | Messaging channels | ⬜ | |
| 13 | Inbox & handoff | ⬜ | |
| 14 | Analytics & metering | ⬜ | |
| 15 | API keys/webhooks/audit | ⬜ | |
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
