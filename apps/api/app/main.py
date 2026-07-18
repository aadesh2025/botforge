"""BotForge API application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.routers import health
from app.channels.router import router as channels_router
from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RequestContextMiddleware
from app.modules.agents.router import router as agents_router
from app.modules.analytics.router import router as analytics_router
from app.modules.apikeys.router import router as apikeys_router
from app.modules.audit.router import router as audit_router
from app.modules.auth.router import router as auth_router
from app.modules.conversations.router import router as conversations_router
from app.modules.credentials.router import router as credentials_router
from app.modules.inbox.router import router as inbox_router
from app.modules.knowledge.router import router as knowledge_router
from app.modules.orgs.router import router as orgs_router
from app.modules.public.router import router as public_router
from app.tools.router import router as tools_router
from app.webhooks.router import router as webhooks_router

log = get_logger("app")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    log.info("startup", env=settings.env, version=__version__)
    _warn_missing_secrets()
    yield
    log.info("shutdown")


def _warn_missing_secrets() -> None:
    """Loudly note stubbed features so the human knows what to fill in (CLAUDE.md §7)."""
    if settings.secret_key == "dev-insecure-change-me" and settings.is_prod:
        log.warning("insecure_secret_key", hint="Set SECRET_KEY in production")
    if not settings.groq_api_key:
        log.warning("missing_key", provider="groq", effect="stubbed; set GROQ_API_KEY")
    if not settings.n8n_api_key:
        log.warning("missing_key", service="n8n", effect="disabled; set N8N_API_KEY")


def create_app() -> FastAPI:
    app = FastAPI(
        title="BotForge API",
        version=__version__,
        description="AI chatbot & automation platform — backend API.",
        lifespan=lifespan,
    )

    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        # In dev, accept any localhost port so the web dev server works whatever port it grabs.
        allow_origin_regex=r"http://localhost:\d+" if not settings.is_prod else None,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(auth_router)
    app.include_router(orgs_router)
    app.include_router(credentials_router)
    app.include_router(agents_router)
    app.include_router(knowledge_router)
    app.include_router(conversations_router)
    app.include_router(tools_router)
    app.include_router(public_router)
    app.include_router(channels_router)
    app.include_router(inbox_router)
    app.include_router(analytics_router)
    app.include_router(apikeys_router)
    app.include_router(webhooks_router)
    app.include_router(audit_router)

    return app


app = create_app()
