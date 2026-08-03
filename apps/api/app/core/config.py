"""Application settings, loaded from environment / .env (see docs/ENV.md)."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _is_comment_only(value: str) -> bool:
    """True when a raw env value is nothing but an unfilled placeholder comment.

    `.env.example` documents unset variables as `KEY=<spaces># [HUMAN] note`. python-dotenv
    strips a trailing comment only when the value has *something* before it — its rule is
    `re.sub(r"\\s+#.*", "", value)`, which needs whitespace ahead of the `#`. On a blank line
    the spaces after `=` are already eaten as the separator, so the `#` lands at position 0,
    the rule can't match, and the comment text becomes the value. `KEY=dev  # note` is
    unaffected (it parses to `dev`), which is why this went unnoticed for so long.
    """
    return value.lstrip().startswith("#")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Core ---
    env: Literal["dev", "test", "prod"] = "dev"
    log_level: str = "info"
    secret_key: str = Field(default="dev-insecure-change-me")
    api_base_url: str = "http://localhost:8000"
    web_base_url: str = "http://localhost:3000"
    cors_origins: str = "http://localhost:3000,http://localhost:3001"

    # --- Datastores (compose defaults; override via env) ---
    database_url: str = "postgresql+asyncpg://botforge:botforge@localhost:5432/botforge"
    redis_url: str = "redis://localhost:6379/0"

    # --- LLM providers (free-first). None = feature stubbed, logged, skipped. ---
    groq_api_key: str | None = None
    gemini_api_key: str | None = None
    openrouter_api_key: str | None = None
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    ollama_base_url: str = "http://localhost:11434"
    embedding_provider: str = "ollama"
    embedding_model: str = "nomic-embed-text"

    # --- Knowledge base / RAG ---
    # Directory for uploaded/ingested document files (created on demand).
    upload_dir: str = "./var/uploads"
    # Ceiling on characters of retrieved context injected into a prompt (token budgeting).
    rag_context_char_budget: int = 8000
    # Run Celery tasks inline (no broker/worker) — handy in dev/tests. Off in prod.
    celery_task_always_eager: bool = False
    # Force every chat + embedding call onto the deterministic Fake provider,
    # regardless of the agent's configured provider. Test/E2E only — lets CI run
    # the full product flows with no paid keys and no local model pulls. Never in prod.
    llm_force_fake: bool = False

    # --- Chat runtime / memory ---
    # How many recent turns (user+assistant messages) to keep verbatim in the prompt.
    memory_window_messages: int = 12
    # Once a conversation exceeds this many messages, older turns are summarized.
    memory_summary_threshold: int = 24
    # Summarizer provider/model — deliberately a small/fast model, NOT the agent's model
    # (so a heavy local model like qwen3:14b never gets used for background summaries).
    summary_provider: str = "groq"
    summary_model: str = "llama-3.1-8b-instant"

    # --- Guardrails (docs/11) ---
    # Hard ceiling on a single visitor message. Also the LLM10 unbounded-consumption control:
    # without it, one caller can push an arbitrarily large prompt through a paid provider.
    max_user_message_chars: int = 8000
    # L1 static pre-filter on the visitor's own message (direct prompt injection, OWASP LLM01).
    # Off means BotForge defends retrieved content but not the person typing — the docs/11 §1.1
    # asymmetry. Kept switchable because a false positive costs a real customer a real answer.
    guard_input_enabled: bool = True
    # L5 output guardrail: system-prompt leakage + persona breaks.
    guard_output_enabled: bool = True
    # Fraction of the assembled system prompt's 8-grams that may appear in a reply before it
    # is treated as leakage. Low enough to catch paraphrase-free quoting, high enough that a
    # reply legitimately reusing the agent's own vocabulary is not suppressed.
    guard_output_leak_threshold: float = 0.35
    # L5 PII egress: redact emails/phones from a reply unless the org allowlisted them.
    guard_pii_egress_enabled: bool = True
    # Regions used to read phone numbers written *without* a country code. Numbers written
    # with an explicit +CC are found regardless. Comma-separated ISO codes, most likely first.
    guard_pii_phone_regions: str = "IN,US,GB"
    # Street-address detection is materially less precise than email/phone ("12 Month Plan"
    # reads as a house number), so it ships flag-only: counted in a document's `pii_flags`,
    # never redacted from a reply, until the false-positive rate is measured on real traffic.
    guard_pii_redact_addresses: bool = False

    # --- Tools (Phase 9) ---
    # Max tool-call iterations per turn before the runtime forces a final answer.
    tool_max_iterations: int = 4
    # Per-tool execution timeout (seconds) for HTTP / built-in tools.
    tool_timeout_seconds: float = 15.0

    # How often (seconds) the Celery beat sweep re-enqueues due `pending` webhook deliveries.
    webhook_sweep_interval_seconds: float = 60.0

    # --- n8n ---
    n8n_base_url: str = "http://localhost:5678"
    n8n_api_key: str | None = None
    n8n_webhook_signing_secret: str | None = None

    # --- Auth / rate limiting ---
    auth_rate_limit: int = 30
    auth_rate_window: int = 60  # seconds
    oauth_redirect_base: str = "http://localhost:8000"

    # --- OAuth (None = provider hidden/denied) ---
    google_client_id: str | None = None
    google_client_secret: str | None = None
    github_client_id: str | None = None
    github_client_secret: str | None = None

    # --- Test-only switches (never enable in production) ---
    # Lets a non-staff user create an organization. BotForge is provisioned per client, so
    # production must leave this off — with it on, anyone who can reach /signup can hand
    # themselves a workspace. It exists because the test suites bootstrap a tenant per test
    # through the public API, the same reason `llm_force_fake` exists.
    allow_self_serve_orgs: bool = False

    # --- Email ---
    # `console` logs to an in-memory outbox (dev/test). `smtp` delivers for real through any
    # SMTP relay — Resend/Postmark/SendGrid/SES/Mailgun all speak it, so switching provider is
    # an env change, never a code change.
    email_backend: Literal["console", "smtp"] = "console"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_pass: str = ""
    smtp_from: str = ""
    # How long a request will wait to hand an email to the queue before giving up on it.
    # Small on purpose: the queue being unreachable must not become the user's problem.
    email_enqueue_timeout_seconds: float = 2.0

    # --- Observability ---
    sentry_dsn: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _drop_placeholder_comments(cls, data: object) -> object:
        """An unfilled `.env` placeholder must read as *unset*, never as its own comment text.

        Root cause of a live outage (ADR-044): `GEMINI_API_KEY=<blank># [HUMAN] Google Gemini
        free tier` resolved to the literal string `# [HUMAN] Google Gemini free tier`, which is
        non-empty — so it sailed past every "is a key configured?" guard and was sent to Google
        as a real API key. Gemini rejected it, and the published agent answered every visitor
        with empty content and HTTP 200 for an unknown period. `SENTRY_DSN` failed the same way
        (`sentry_init_failed: Unsupported scheme ''`).

        Only a *comment-only* value is dropped, and dropping it lets the field's own default
        apply. Deliberately NOT "strip everything after the first `#`": values legitimately
        contain that character — `SECRET_KEY=abc#def`, a DB password, a URL fragment — and a
        blanket strip would silently truncate them, trading this bug for a worse one. The one
        false positive is a real secret that *starts* with `#`; it degrades to "not configured",
        which is loud and well-trodden, rather than to garbage-that-looks-configured.
        """
        if not isinstance(data, dict):
            return data
        return {k: v for k, v in data.items() if not (isinstance(v, str) and _is_comment_only(v))}

    @field_validator("smtp_port", mode="before")
    @classmethod
    def _blank_port_is_the_default(cls, v: object) -> object:
        """`SMTP_PORT=` (blank, as shipped in .env.example) means "use the default", not a crash.

        Same blank-is-unset convention ADR-020 applied to env-provided provider keys — an
        unfilled placeholder must never stop the app booting.
        """
        return 587 if v is None or (isinstance(v, str) and not v.strip()) else v

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_prod(self) -> bool:
        return self.env == "prod"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
