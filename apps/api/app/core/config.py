"""Application settings, loaded from environment / .env (see docs/ENV.md)."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # --- Tools (Phase 9) ---
    # Max tool-call iterations per turn before the runtime forces a final answer.
    tool_max_iterations: int = 4
    # Per-tool execution timeout (seconds) for HTTP / built-in tools.
    tool_timeout_seconds: float = 15.0

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

    # --- Email ---
    email_backend: Literal["console", "smtp"] = "console"

    # --- Observability ---
    sentry_dsn: str | None = None

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
