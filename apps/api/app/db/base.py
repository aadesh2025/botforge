"""Declarative base, common mixins, and a UUIDv7 generator.

UUIDv7 is time-ordered, which keeps primary-key index inserts local (better than v4).
Python's stdlib has no uuid7 yet, so we build one from a 48-bit millisecond timestamp
plus random bits, per the RFC 9562 layout.
"""

from __future__ import annotations

import datetime as dt
import os
import time
import uuid

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def uuid7() -> uuid.UUID:
    """Generate a time-ordered UUIDv7 (RFC 9562)."""
    unix_ms = int(time.time() * 1000)
    rand = os.urandom(10)
    raw = bytearray(unix_ms.to_bytes(6, "big") + rand)
    raw[6] = (raw[6] & 0x0F) | 0x70  # version 7
    raw[8] = (raw[8] & 0x3F) | 0x80  # variant 10
    return uuid.UUID(bytes=bytes(raw))


class Base(DeclarativeBase):
    """Declarative base for all models."""


class UUIDPrimaryKey:
    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid7
    )


class TimestampMixin:
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class SoftDeleteMixin:
    deleted_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
