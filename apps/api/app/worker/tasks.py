"""Celery tasks. Each task owns its own committing DB session (separate from request scope)."""

from __future__ import annotations

import asyncio
import datetime as dt
import uuid
from collections.abc import Coroutine
from typing import TypeVar

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.logging import get_logger
from app.rag.ingest import ingest_document
from app.worker.celery_app import celery_app
from app.worker.rollup import rollup_org

log = get_logger("worker.tasks")

_T = TypeVar("_T")

# Celery runs each task on a *fresh* ``asyncio.run`` event loop. A pooled asyncpg
# connection bound to a previous task's (now-closed) loop raises "Event loop is closed"
# / "'NoneType' object has no attribute 'send'" when reused. A dedicated worker engine
# with NullPool never reuses a connection across loops: every session opens and closes
# its own connection on the current loop. Kept separate from the API's pooled engine.
_worker_engine = create_async_engine(settings.database_url, poolclass=NullPool, pool_pre_ping=False)
SessionFactory = async_sessionmaker(bind=_worker_engine, expire_on_commit=False, autoflush=False)


def _run(coro: Coroutine[object, object, _T]) -> _T:
    """Run one task coroutine on a fresh event loop (NullPool means no cross-loop reuse)."""
    return asyncio.run(coro)


async def _run_ingest(document_id: uuid.UUID) -> str:
    async with SessionFactory() as session:
        document = await ingest_document(session, document_id)
        await session.commit()
        return document.status


@celery_app.task(name="rag.ingest_document", bind=True, max_retries=2)  # type: ignore[untyped-decorator]
def ingest_document_task(self: object, document_id: str) -> str:
    """Parse/chunk/embed/store a document. Idempotent: re-running replaces its chunks."""
    log.info("ingest_task_start", document_id=document_id)
    return _run(_run_ingest(uuid.UUID(document_id)))


def enqueue_document_ingestion(document_id: uuid.UUID) -> None:
    """Enqueue ingestion. Indirection kept small so services/tests can stub it out."""
    ingest_document_task.delay(str(document_id))


async def _run_rollup(org_id: str, date_str: str) -> dict[str, int]:
    async with SessionFactory() as session:
        result = await rollup_org(session, uuid.UUID(org_id), dt.date.fromisoformat(date_str))
        await session.commit()
        return result


@celery_app.task(name="usage.rollup_org")  # type: ignore[untyped-decorator]
def rollup_org_task(org_id: str, date_str: str) -> dict[str, int]:
    """Roll up one org's usage for a date into usage_records + refresh its quota."""
    return _run(_run_rollup(org_id, date_str))


async def _run_delivery(delivery_id: str) -> bool:
    from app.webhooks.dispatch import deliver_delivery

    async with SessionFactory() as session:
        ok = await deliver_delivery(session, uuid.UUID(delivery_id))
        await session.commit()
        return ok


@celery_app.task(name="webhooks.deliver", bind=True, max_retries=5)  # type: ignore[untyped-decorator]
def deliver_webhook_task(self: object, delivery_id: str) -> bool:
    """Attempt one webhook delivery; Celery retries with backoff on failure."""
    ok = _run(_run_delivery(delivery_id))
    if not ok:
        raise self.retry(countdown=min(3600, 30), exc=RuntimeError("delivery not confirmed"))  # type: ignore[attr-defined]
    return ok


async def _run_sweep() -> int:
    from app.webhooks.dispatch import sweep_due_deliveries

    async with SessionFactory() as session:
        n = await sweep_due_deliveries(session)
        await session.commit()
        return n


@celery_app.task(name="webhooks.sweep_pending")  # type: ignore[untyped-decorator]
def sweep_pending_webhooks_task() -> int:
    """Periodic (Celery beat) safety-net: re-enqueue due `pending` webhook deliveries."""
    return _run(_run_sweep())
