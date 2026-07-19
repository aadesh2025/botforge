# 09 — Deployment, Infra & Ops

## 1. Dev environment (`infra/docker-compose.yml`)
Services (single command `docker compose up`):
- **postgres** — `pgvector/pgvector:pg16` image; volume `pgdata`; healthcheck `pg_isready`.
- **redis** — `redis:7`; volume; healthcheck `redis-cli ping`.
- **api** — build `apps/api`; depends_on postgres+redis healthy; runs migrations on start
  (entrypoint: `alembic upgrade head` then uvicorn); mounts code for hot reload in dev.
- **worker** — same image as api; command runs Celery worker (+ `beat` for scheduled rollups).
- **web** — build `apps/web`; `next dev`; proxies to api.
- **n8n** — `n8nio/n8n`; port 5678; volume `n8ndata`; env for basic auth + `N8N_API_KEY`.
- **ollama** — `ollama/ollama`; port 11434; volume; pull `nomic-embed-text` (+ a small chat
  model) via an init step for fully-local free operation.

All secrets/config come from `.env` (never committed). `.env.example` documents each.
Also support pointing at an **already-running** n8n/ollama via `N8N_BASE_URL`/`OLLAMA_BASE_URL`
instead of the bundled services.

## 2. Environment variables (source of truth: `docs/ENV.md`)
Groups: core (`SECRET_KEY`, `DATABASE_URL`, `REDIS_URL`, `ENV`), LLM (`GROQ_API_KEY`,
`GEMINI_API_KEY`, `OPENROUTER_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`,
`OLLAMA_BASE_URL`), OAuth (`GOOGLE_CLIENT_ID/SECRET`, `GITHUB_CLIENT_ID/SECRET`), channels
(`TELEGRAM_BOT_TOKEN`, `META_APP_SECRET`/WhatsApp tokens, Slack/Discord secrets), n8n
(`N8N_BASE_URL`, `N8N_API_KEY`), email (`SMTP_*` or dev console), billing (`STRIPE_*`),
observability (`SENTRY_DSN`). Every var: name, purpose, required?, default, "needs human?".

## 3. Production (`infra/docker-compose.prod.yml`)
- Reverse proxy: **Caddy** (auto-TLS) or Nginx; terminates HTTPS, routes `/api`→api, `/`→web,
  serves `widget.js`. Security headers + CSP configured here.
- Images: multi-stage, non-root user, pinned base images, no dev deps.
- API/worker/web replicated behind proxy; postgres + redis with persistent volumes.
- Run migrations as a one-shot job on deploy (not on every replica start).
- Resource limits, restart policies, healthchecks, log driver (json/loki).

## 4. Backups & data  *(implemented)*
- **`infra/scripts/backup.sh`** — `pg_dump | gzip` to a timestamped file with N-day rotation.
  Run it nightly via cron (example in the script header) or as a one-shot container that can
  reach Postgres. The prod compose ships a `backup` service (cron-driven) writing to a `backups` volume.
- **`infra/scripts/restore.sh <file.sql.gz>`** — documented, confirmation-gated restore (with an
  optional drop+recreate). Verify with `SELECT count(*) FROM organizations;`.
- Uploaded files: local volume (`UPLOAD_DIR`) in dev; back that path up alongside the DB (or point
  it at an S3-compatible bucket in prod). Retention + delete-per-org honored (NFR-8).

## 5. Observability  *(implemented)*
- `/healthz` (liveness), `/readyz` (DB+Redis), **`/metrics` (Prometheus exposition** — request
  counts by method/status, a latency histogram, build info + uptime; scrape it from Prometheus).
- **Structured JSON logs** to stdout with request/org/user ids (`configure_logging`) — 12-factor,
  so any aggregator (Loki/Promtail, CloudWatch, ELK, Datadog) collects them from the container's
  stdout with no app change. Set `LOG_LEVEL` per environment.
- **Sentry** error tracking auto-initialized when `SENTRY_DSN` is set (`_init_sentry`, 10% traces,
  no PII); a no-op otherwise.
- LLM call tracing (provider/model/tokens/latency/cost/fallback) recorded on every message.

## 6. CI/CD (`.github/workflows/`)
- **ci.yml**: on push/PR — install, lint (`ruff`,`eslint`), typecheck (`mypy`,`tsc`), unit
  tests (`pytest`,`vitest`), build web, spin compose + run Playwright E2E, upload artifacts.
- **release.yml**: on tag — build & push api/web images to registry, run migrations, deploy
  (compose over SSH or к8s), smoke test `/readyz`.
- Cache deps; fail the pipeline on any lint/type/test error (matches Definition of Done).

## 7. Scaling notes
- API is stateless → scale horizontally behind the proxy. Celery workers scale independently.
- Postgres connection pooling (pgbouncer optional). Redis for cache/rate-limit/queue.
- pgvector index (HNSW) tuned for recall/latency; consider Qdrant swap-in later (interface
  already abstracts the vector store).

## 8. Kubernetes (stretch, `infra/k8s/`)
Deployments for api/worker/web, StatefulSets for postgres/redis (or managed), Services,
Ingress (TLS), ConfigMaps/Secrets, HPA on api/worker, Job for migrations. Or a Helm chart.
Deferring is acceptable — record in `PROGRESS.md`.

## 9. Runbooks (`docs/` after build)
Self-host guide, restore-from-backup, rotate secrets, add an LLM provider key, connect a
channel, import n8n starter workflows, scale workers, incident basics.
