# 05 — Frontend (Next.js 14 Dashboard + Design System)

## 1. Stack & conventions
- Next.js 14 App Router, TypeScript strict, Tailwind CSS, **shadcn/ui** components, Framer
  Motion for motion, **TanStack Query** for server state, **Zustand** for local UI state,
  `react-hook-form` + `zod` for forms, `next-themes` for dark mode.
- Typed API client generated from backend `openapi.json` (e.g., `openapi-typescript` +
  a thin fetch wrapper). No `any`. All network calls go through `lib/api`.
- Auth: access token in httpOnly cookie; a Next.js route handler proxies refresh. Middleware
  guards `/app/*` routes. Server components fetch with the cookie; client components use the
  query client.
- Accessibility: keyboard nav, focus states, ARIA, color-contrast AA.

## 2. Route map (App Router)
```
/(marketing)
  /                     landing page
  /pricing, /docs       simple static (stretch)
/(auth)
  /login /signup /forgot /reset /verify /magic
/(app)                  authenticated dashboard (org-scoped, org switcher in shell)
  /dashboard            org overview: agents, recent convos, usage snapshot
  /agents               list + create
  /agents/[id]          agent builder (tabs below)
     ?tab=persona | model | knowledge | tools | channels | playground | versions | settings
  /knowledge            knowledge bases list
  /knowledge/[id]       documents, upload, ingestion status, chunk viewer, search test
  /inbox                live conversations + handoff
  /inbox/[cid]          conversation view + operator reply
  /analytics            dashboards (overview, usage/cost, latency, top/unanswered questions)
  /automations          n8n workflows list + bind as tools
  /settings/org         org profile, members, invitations, roles
  /settings/credentials provider API keys (BYO)
  /settings/api-keys    programmatic keys
  /settings/webhooks    outbound webhook endpoints
  /settings/billing     subscription (optional)
  /settings/profile     user profile, sessions
/(admin)                platform staff only
  /admin                orgs, users, usage, health, feature flags
```

## 3. App shell
- Left sidebar nav, top bar with **org switcher**, user menu, theme toggle, notifications.
- Responsive: sidebar collapses on mobile. Command palette (⌘K) for quick nav (stretch).

## 4. Agent builder (the centerpiece — maps to FR-C / 06-AI-ENGINE §4)
Tabbed editor over the current draft `agent_version`, with a persistent **Playground** panel
on the right (or a tab) to chat with the draft, and a **Publish** button.

- **Persona tab**: name, avatar upload, system prompt (big editor with token counter),
  character, role, tone selector, guardrails (blocked topics list), welcome message,
  fallback message, suggested prompts (repeatable inputs).
- **Model tab**: provider select (Groq default, then Gemini/Ollama/OpenRouter/OpenAI/
  Anthropic/custom), model dropdown (populated from `/v1/credentials/providers`), sliders
  for temperature/top_p/max_tokens/penalties, stop sequences, fallback providers,
  credential selector (org default vs BYO key vs custom base_url).
- **Knowledge tab**: attach knowledge bases, set top_k / score_threshold / hybrid toggle,
  quick "test retrieval" box.
- **Tools tab**: toggle built-in tools, create HTTP tools (form: method/url/headers/body
  schema/auth), bind n8n workflows, test a tool, view recent runs.
- **Channels tab**: manage widget (theme/colors/position/branding preview), connect Telegram/
  WhatsApp/Slack/Discord (guided forms), copy embed snippet.
- **Playground**: streaming chat with token counter, shows citations + tool calls inline;
  uses the draft version.
- **Versions tab**: list versions, diff, publish, rollback.

## 5. Knowledge UI
Upload dropzone (PDF/DOCX/TXT/CSV/MD) + add URL + paste text. Documents table with live
status badges (queued/processing/ready/failed) and progress; row actions reindex/delete/view
chunks. Chunk viewer with content + metadata. Retrieval test box.

## 6. Inbox UI
Two-pane: conversation list (filter by status/channel/agent) + conversation thread. Operator
can take over (pauses bot), type replies (streamed to end user), add notes/tags, assign,
close, hand back to bot. Real-time updates via WS.

## 7. Analytics UI
Date-range picker + agent filter. Cards (conversations, messages, users, resolution %,
handoff %). Charts (Recharts): messages over time, tokens & cost over time by provider,
latency distribution, top questions, unanswered questions. CSV export buttons.

## 8. Design system
- **Tokens**: colors (brand primary + neutrals, semantic success/warn/error), spacing scale,
  radius, shadows, typography scale. Support light/dark via CSS variables + `next-themes`.
- **Components** (shadcn/ui base + custom): Button, Input, Textarea, Select, Slider, Switch,
  Tabs, Dialog/Sheet, DropdownMenu, Table (with pagination), Badge, Toast, Card, Avatar,
  Tooltip, Skeleton, EmptyState, FileDropzone, CodeBlock/SnippetCopy, ChatBubble, Streaming
  message, StatusBadge, Chart wrappers, OrgSwitcher, RoleGuard.
- **Motion**: subtle enter/exit, streaming caret, skeleton loaders. Respect
  `prefers-reduced-motion`.
- **States**: every list/detail has loading (skeleton), empty, and error states.

## 9. Frontend testing
- Vitest + Testing Library for components/hooks.
- Playwright E2E for the critical journeys (see `10-TESTING.md`).
- Mock the API in unit tests; run E2E against the real stack via docker compose.

## 10. Performance
- Server components + streaming; route-level code splitting; image optimization; TanStack
  Query caching + optimistic updates for builder edits; debounced autosave of draft versions.
