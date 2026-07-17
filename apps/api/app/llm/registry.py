"""Provider catalog, factory, credential resolution, and the fallback runner."""

from __future__ import annotations

import uuid
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.crypto import decrypt
from app.core.errors import AppError
from app.llm.anthropic import AnthropicProvider
from app.llm.base import ChatProvider, ProviderError
from app.llm.fake import FakeChatProvider
from app.llm.gemini import GeminiProvider
from app.llm.openai_compatible import (
    CustomProvider,
    GroqProvider,
    OllamaProvider,
    OpenAIProvider,
    OpenRouterProvider,
)
from app.llm.types import ChatRequest, ChatResponse
from app.models import ProviderCredential

# provider -> catalog metadata. `requires_key`: needs an API key to work at all.
PROVIDER_CATALOG: dict[str, dict[str, Any]] = {
    "groq": {
        "label": "Groq",
        "free": True,
        "requires_key": True,
        "models": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768", "gemma2-9b-it"],
    },
    "gemini": {
        "label": "Google Gemini",
        "free": True,
        "requires_key": True,
        "models": ["gemini-1.5-flash", "gemini-1.5-pro"],
    },
    "ollama": {"label": "Ollama (local)", "free": True, "requires_key": False, "models": ["llama3.1", "qwen2.5"]},
    "openrouter": {
        "label": "OpenRouter",
        "free": True,
        "requires_key": True,
        "models": ["meta-llama/llama-3.1-70b-instruct:free"],
    },
    "openai": {
        "label": "OpenAI",
        "free": False,
        "requires_key": True,
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4.1-mini"],
    },
    "anthropic": {
        "label": "Anthropic",
        "free": False,
        "requires_key": True,
        "models": ["claude-sonnet-5", "claude-haiku-4-5-20251001"],
    },
    "custom": {"label": "Custom endpoint", "free": True, "requires_key": False, "models": []},
}

_ENV_KEY = {
    "groq": "groq_api_key",
    "gemini": "gemini_api_key",
    "openrouter": "openrouter_api_key",
    "openai": "openai_api_key",
    "anthropic": "anthropic_api_key",
}


def build_chat_provider(
    provider: str,
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> ChatProvider:
    if provider == "groq":
        return GroqProvider(api_key, transport=transport)
    if provider == "gemini":
        return GeminiProvider(api_key, transport=transport)
    if provider == "ollama":
        return OllamaProvider(api_key, base_url=base_url, transport=transport)
    if provider == "openrouter":
        return OpenRouterProvider(api_key, transport=transport)
    if provider == "openai":
        return OpenAIProvider(api_key, transport=transport)
    if provider == "anthropic":
        return AnthropicProvider(api_key, transport=transport)
    if provider == "custom":
        if not base_url:
            raise AppError("llm.custom_base_url_required", "A base_url is required for custom providers.", 400)
        return CustomProvider(base_url, api_key, transport=transport)
    if provider == "fake":
        return FakeChatProvider()
    raise AppError("llm.unknown_provider", f"Unknown provider '{provider}'.", 400)


async def resolve_credential(
    session: AsyncSession, org_id: uuid.UUID, provider: str, *, agent_id: uuid.UUID | None = None
) -> tuple[str | None, str | None]:
    """Key lookup order: agent-scoped credential → org default → platform env key."""
    stmt = select(ProviderCredential).where(
        ProviderCredential.organization_id == org_id, ProviderCredential.provider == provider
    )
    creds = list((await session.execute(stmt)).scalars().all())

    def _pick() -> ProviderCredential | None:
        if agent_id is not None:
            for c in creds:
                if c.agent_id == agent_id:
                    return c
        for c in creds:
            if c.is_default and c.agent_id is None:
                return c
        for c in creds:
            if c.agent_id is None:
                return c
        return None

    chosen = _pick()
    if chosen is not None:
        api_key = decrypt(chosen.api_key_enc) if chosen.api_key_enc else None
        return api_key, chosen.base_url

    env_attr = _ENV_KEY.get(provider)
    env_key = getattr(settings, env_attr) if env_attr else None
    return env_key, None


async def get_chat_provider(
    session: AsyncSession,
    org_id: uuid.UUID,
    provider: str,
    *,
    agent_id: uuid.UUID | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> ChatProvider:
    api_key, base_url = await resolve_credential(session, org_id, provider, agent_id=agent_id)
    meta = PROVIDER_CATALOG.get(provider, {})
    if meta.get("requires_key", True) and not api_key:
        raise AppError(
            "llm.provider_unavailable",
            f"No API key configured for '{provider}'. Add one under provider credentials.",
            503,
        )
    return build_chat_provider(provider, api_key=api_key, base_url=base_url, transport=transport)


async def run_with_fallback(providers: list[ChatProvider], req: ChatRequest) -> ChatResponse:
    """Try each provider in order; on a provider failure, fall back to the next."""
    if not providers:
        raise AppError("llm.provider_unavailable", "No providers available.", 503)
    last_error: Exception | None = None
    for provider in providers:
        try:
            return await provider.chat(req)
        except ProviderError as exc:
            last_error = exc
    raise AppError("llm.provider_unavailable", f"All providers failed: {last_error}", 502)
