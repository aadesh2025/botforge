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
    cors_origins: str = "http://localhost:3000"

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
