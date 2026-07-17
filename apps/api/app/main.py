"""BotForge API application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.routers import health
from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RequestContextMiddleware
from app.modules.agents.router import router as agents_router
from app.modules.auth.router import router as auth_router
from app.modules.credentials.router import router as credentials_router
from app.modules.orgs.router import router as orgs_router

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

    return app


app = create_app()
