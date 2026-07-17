# ENV.md — Environment Variables

Every variable BotForge reads. Mirror these as placeholders in `.env.example`. "Needs human"
= only the human can create it; if unset, the code must stub the feature, log a loud warning,
and keep building (`CLAUDE.md §7`).

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
`TELEGRAM_BOT_TOKEN`; WhatsApp `META_APP_SECRET`, `WHATSAPP_PHONE_ID`, `WHATSAPP_TOKEN`,
`WHATSAPP_VERIFY_TOKEN`; Slack `SLACK_BOT_TOKEN`, `SLACK_SIGNING_SECRET`; Discord
`DISCORD_BOT_TOKEN`, `DISCORD_PUBLIC_KEY`. All needs-human; unset → channel disabled with a
clear message.

## n8n
| Var | Purpose | Needs human |
|---|---|---|
| `N8N_BASE_URL` | n8n REST/webhook base (default `http://n8n:5678`) | no |
| `N8N_API_KEY` | n8n public API auth | yes (from n8n UI) |
| `N8N_WEBHOOK_SIGNING_SECRET` | sign BotForge→n8n calls | generate |

## Email
`SMTP_HOST/PORT/USER/PASS/FROM` or `EMAIL_BACKEND=console` (dev). Console needs no human.

## Billing (optional)
`STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_*` — needs-human; unset → billing
disabled.

## Observability
`SENTRY_DSN` (optional), `LOG_LEVEL` (default info).

## Storage
`STORAGE_BACKEND=local|s3`; if s3: `S3_ENDPOINT/BUCKET/ACCESS_KEY/SECRET_KEY` — needs-human
for prod; local default in dev.
