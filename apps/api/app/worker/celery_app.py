"""Celery application. Broker/result backend = Redis (docs/02)."""

from __future__ import annotations

from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "botforge",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.worker.tasks"],
)

celery_app.conf.update(
    task_always_eager=settings.celery_task_always_eager,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    timezone="UTC",
    enable_utc=True,
)
