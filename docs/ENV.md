# ENV.md — Environment Variables

Every variable BotForge reads. Mirror these as placeholders in `.env.example`. "Needs human"
= only the human can create it; if unset, the code must stub the feature, log a loud warning,
and keep building (`CLAUDE.md §7`).

## Writing `.env` — one formatting rule

**A comment must never share a line with a blank value.**

```dotenv
# [HUMAN] Google Gemini free tier      ← correct: comment on its own line
GEMINI_API_KEY=

GEMINI_API_KEY=      # [HUMAN] ...     ← WRONG: the comment becomes the value
```

`KEY=value  # note` is fine and parses to `value` — the loader strips a comment only when
something precedes it. On a blank line the spaces after `=` are eaten as the separator, so the
`#` starts the value and the whole comment is read as the secret. That sent a placeholder to
Google as a real API key and took a live agent down silently (ADR-044).

`Settings` now drops comment-only values defensively, so an existing `.env` in the old shape
still behaves. Do not rely on it: `.env` is also passed to containers via compose's `env_file`,
which parses the file with its own rules that the Python fix cannot reach.

## Core
| Var | Purpose | Required | Default | Needs human |
|---|---|---|---|---|
| `ENV` | dev/test/prod | yes | dev | no |
| `SECRET_KEY` | JWT signing + key encryption | yes | — | yes (generate) |
| `DATABASE_URL` | Postgres async DSN | yes | compose default | no |
| `REDIS_URL` | Redis DSN | yes | compose default | no |
| `API_BASE_URL` / `WEB_BASE_URL` | absolute URLs | yes | localhost | no |

## LLM providers (free-first)
| Var | Purpose | Needs human |
|---|---|---|
| `GROQ_API_KEY` | default provider | yes (free signup) |
| `GEMINI_API_KEY` | Google Gemini free tier | yes |
| `OPENROUTER_API_KEY` | free models via OpenRouter | yes |
| `OLLAMA_BASE_URL` | local models + embeddings | no (bundled) |
| `OPENAI_API_KEY` | paid | yes |
| `ANTHROPIC_API_KEY` | paid | yes |
| `EMBEDDING_PROVIDER` / `EMBEDDING_MODEL` | default embeddings | no |

## OAuth
`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET` — all
needs-human (create OAuth apps). Unset → hide/deny those login buttons.

## Channels
`TELEGRAM_BOT_TOKEN`; Slack `SLACK_BOT_TOKEN`, `SLACK_SIGNING_SECRET`; Discord
`DISCORD_BOT_TOKEN`, `DISCORD_PUBLIC_KEY`. All needs-human; unset → channel disabled with a
clear message.

### Meta surfaces (WhatsApp, Messenger, Instagram)
All three ride one Meta app, so they share `META_APP_SECRET` — the key behind the
`X-Hub-Signature-256` check every inbound delivery must pass.

| Var | Surface | Needs human |
|---|---|---|
| `META_APP_SECRET` | all three — webhook signature verification | yes |
| `META_VERIFY_TOKEN` | all three — echoed back during Meta's `hub.challenge` handshake | no (you choose it) |
| `WHATSAPP_PHONE_ID`, `WHATSAPP_TOKEN`, `WHATSAPP_VERIFY_TOKEN` | WhatsApp Cloud API | yes |
| `META_PAGE_ID`, `META_PAGE_ACCESS_TOKEN` | Facebook Messenger DMs + profile lookups | yes |
| `INSTAGRAM_USER_ID`, `INSTAGRAM_PAGE_ACCESS_TOKEN` | Instagram DMs; needs `instagram_manage_messages` | yes |

These are reference values for the human — each channel's real credentials are entered per
agent in **Builder → Channels** and stored encrypted in `channels.config`. Unset → the
adapter logs a loud warning and skips sending/profile lookups, but still accepts and
persists inbound messages (CLAUDE.md §7).

Profile/avatar support differs by platform, and that's the platform's doing, not a gap:
Messenger and Instagram return a name *and* photo via the Graph API; WhatsApp Cloud API
sends a profile name but has no photo endpoint; Telegram carries the name in the update but
serves photos from token-bearing URLs we deliberately never persist (see ADR-036).

## n8n
| Var | Purpose | Needs human |
|---|---|---|
| `N8N_BASE_URL` | n8n REST/webhook base (default `http://n8n:5678`) | no |
| `N8N_HOST_PORT` | host port the bundled n8n binds (default `5678`); must agree with `N8N_BASE_URL`. **Compose-only** — read from the shell or `infra/.env`, not from the root `.env` (which is passed to containers via `env_file` and so never reaches `${...}` interpolation) | no |
| `N8N_API_KEY` | n8n public API auth — needs the workflow read/list/create/update/activate scopes | yes (from n8n UI) |
| `N8N_WEBHOOK_SIGNING_SECRET` | sign BotForge→n8n calls | generate |

`N8N_HOST_PORT` exists because 5678 is often already taken — on the build machine by an
unrelated n8n belonging to another project. BotForge must not create or activate workflows in
someone else's instance, so point it at its own (`N8N_HOST_PORT=5679`,
`N8N_BASE_URL=http://localhost:5679`). n8n 2.x also binds its editor session cookie to a
`browser-id` header, so minting an API key over `/rest/*` requires sending one; the UI
(Settings → API) is the simpler route.

## Client provisioning (`scripts/provision-client.mjs`)

| Var | Purpose | Needs human |
|---|---|---|
| `BOTFORGE_API_BASE_URL` | which BotForge to provision into (default `http://localhost:8000`) | no |
| `PROVISION_STAFF_EMAIL` | a login with `is_staff=true` | yes |
| `PROVISION_STAFF_PASSWORD` | that account's password | yes |

The script signs in as a **staff user** rather than using a `bf_…` API key: creating an
organization is gated on `User.is_staff` server-side and no key scope grants it. Point
`BOTFORGE_API_BASE_URL`/`N8N_BASE_URL` at localhost today and at the VPS later — that is the
only difference between provisioning on a laptop and provisioning in production.

## Email

Four emails go out: organization invitations, signup verification, password reset, and
magic-link sign-in. All four funnel through one backend chosen by `EMAIL_BACKEND`.

| Var | Purpose | Needs human |
|---|---|---|
| `EMAIL_BACKEND` | `console` (in-memory outbox, dev/test default) or `smtp` (real delivery) | no |
| `SMTP_HOST` | relay hostname, e.g. `smtp.resend.com` | yes |
| `SMTP_PORT` | relay port; blank is read as the default `587` (STARTTLS) | no |
| `SMTP_USER` / `SMTP_PASS` | relay credentials from your provider | yes |
| `SMTP_FROM` | envelope sender, e.g. `BotForge <noreply@yourdomain.com>` | yes |

**Plain SMTP on purpose.** Resend, Postmark, SendGrid, Mailgun and Amazon SES all expose an
SMTP relay with exactly these settings, so changing provider is an env change and never a code
change. Resend or Postmark are the easiest starting points for a solo operator.

**Code alone does not get you delivered mail.** You still have to verify your sending domain
with the provider (SPF/DKIM DNS records — their dashboard walks you through it). Without it the
receiving server has no way to tell your mail from a spoof, and Gmail will bin it.

With `EMAIL_BACKEND=smtp`, sends run on the **Celery worker**, so a slow or dead relay can never
hang or 500 a signup/invite/reset request; failures retry with backoff. `console` sends inline —
there is nothing to protect the request from — which is also what keeps the test outbox
synchronous. If `SMTP_HOST`/`SMTP_FROM` are unset while the backend is `smtp`, a send raises
`email.not_configured` rather than silently dropping the message.

## Billing (optional)
`STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_*` — needs-human; unset → billing
disabled.

## Observability
`SENTRY_DSN` (optional), `LOG_LEVEL` (default info).

## Storage & RAG
`STORAGE_BACKEND=local|s3`; if s3: `S3_ENDPOINT/BUCKET/ACCESS_KEY/SECRET_KEY` — needs-human
for prod; local default in dev.

- `UPLOAD_DIR` (default `./var/uploads`) — filesystem path where ingested document files are
  stored under the local backend. Created on demand; gitignored.
- `RAG_CONTEXT_CHAR_BUDGET` (default `8000`) — ceiling on characters of retrieved context
  injected into a prompt (token budgeting; oldest/lowest-ranked citations are trimmed first).
- `CELERY_TASK_ALWAYS_EAGER` (default `false`) — when true, Celery tasks (document ingestion)
  run inline in-process instead of via the worker/broker. Handy for dev/tests; never in prod.
- `LLM_FORCE_FAKE` (default `false`) — when true, every chat and embedding call is forced onto
  the deterministic Fake provider regardless of the agent's configured provider. Used by the
  Playwright E2E suite so CI needs no paid keys and no local model pulls. **Never set in prod.**

## Chat runtime, memory & tools
- `MEMORY_WINDOW_MESSAGES` (default `12`) — how many recent turns stay verbatim in the prompt.
- `MEMORY_SUMMARY_THRESHOLD` (default `24`) — once a conversation exceeds this many messages,
  older turns are folded into `conversation.memory_summary`.
- `SUMMARY_PROVIDER` / `SUMMARY_MODEL` (default `groq` / `llama-3.1-8b-instant`) — the small,
  fast model used for background memory summaries. Deliberately independent of the agent's own
  model so a heavy local model (e.g. qwen3:14b) is never used for summaries. Falls back to the
  fake provider when the provider has no key (CLAUDE §7).
- `TOOL_MAX_ITERATIONS` (default `4`) — max tool-call iterations per turn before the runtime
  forces a final answer.
- `TOOL_TIMEOUT_SECONDS` (default `15`) — per-tool execution timeout (HTTP / built-in tools).

## Guardrails (docs/11)
- `MAX_USER_MESSAGE_CHARS` (default `8000`) — hard ceiling on a single visitor message. Also
  the OWASP **LLM10** unbounded-consumption control: without it one caller can push an
  arbitrarily large prompt through a paid provider.
- `GUARD_INPUT_ENABLED` (default `true`) — the L1 static pre-filter on the visitor's own
  message (direct prompt injection, **LLM01**). With it off, BotForge still defends retrieved
  documents and tool output but not the person typing — the asymmetry docs/11 §1.1 documents.
  Switchable because a false positive costs a real customer a real answer; the benign fixture
  corpus in `tests/fixtures/redteam/benign.yaml` is what keeps that rate at zero.
- `GUARD_OUTPUT_ENABLED` (default `true`) — the L5 output guardrail: system-prompt leakage and
  persona breaks. Secret redaction runs regardless of this flag.
- `GUARD_OUTPUT_LEAK_THRESHOLD` (default `0.35`) — fraction of a reply's normalised 8-grams
  that may also appear in the assembled system prompt before the reply is treated as a leak
  and replaced. Lower is stricter. Raise it if legitimate answers that reuse the agent's own
  wording are being suppressed; the knowledge-base content is deliberately **not** part of the
  comparison, so quoting retrieved documents never counts.

- `GUARD_PII_EGRESS_ENABLED` (default `true`) — redact emails and phone numbers from a reply
  unless the org has allowlisted them (docs/11 Phase B, ADR-053). Secret redaction runs
  regardless of this flag. The allowlist is `Organization.public_contacts`, **not** an env var:
  it is per-tenant, and an empty one means the agent shares no contact details at all — safe,
  but not useful, so provisioning should seed it with the client's real support address.
- `GUARD_PII_PHONE_REGIONS` (default `IN,US,GB`) — ISO country codes used to read phone numbers
  written *without* a country code, most likely first. Numbers written with an explicit `+CC`
  are found regardless. Add a region when a client's customers write local-format numbers from
  somewhere else; each one is an extra scan pass, so keep the list short.
- `GUARD_PII_REDACT_ADDRESSES` (default `false`) — street addresses are counted in a document's
  `pii_flags` but not redacted from replies. Detection precision is materially worse than
  email/phone ("12 Month Plan" reads as a house number), so this stays off until the
  false-positive rate is measured on real traffic.

> The Playground bypasses the output guardrail entirely, the same way it withholds an agent's
> fallback message and re-raises provider errors: an operator testing an agent has to see what
> the model actually said. Guardrail behaviour is therefore visible on the widget, channels and
> dashboard chat, but not in the builder's test pane.

> **Finding what is already in a knowledge base:** `make audit-kb-pii` scans every KB across
> every org and reports counts per document (never the values). It exits non-zero when anything
> is found. `--apply` backfills `documents.pii_flags` for documents ingested before migration
> 0015; it never edits document text — removing PII from a client's corpus is an operator
> decision (ADR-054).
