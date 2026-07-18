"""Celery tasks. Each task owns its own committing DB session (separate from request scope)."""

from __future__ import annotations

import asyncio
import datetime as dt
import uuid

from app.core.logging import get_logger
from app.db.session import SessionFactory
from app.rag.ingest import ingest_document
from app.worker.celery_app import celery_app
from app.worker.rollup import rollup_org

log = get_logger("worker.tasks")


async def _run_ingest(document_id: uuid.UUID) -> str:
    async with SessionFactory() as session:
        document = await ingest_document(session, document_id)
        await session.commit()
        return document.status


@celery_app.task(name="rag.ingest_document", bind=True, max_retries=2)  # type: ignore[untyped-decorator]
def ingest_document_task(self: object, document_id: str) -> str:
    """Parse/chunk/embed/store a document. Idempotent: re-running replaces its chunks."""
    log.info("ingest_task_start", document_id=document_id)
    return asyncio.run(_run_ingest(uuid.UUID(document_id)))


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
    return asyncio.run(_run_rollup(org_id, date_str))
