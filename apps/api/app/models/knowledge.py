"""Knowledge base, documents, and vector chunks."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKey

# Dimension of the embedding vectors. Matches nomic-embed-text (768); make configurable
# per knowledge base later if a different embedding model is chosen.
EMBEDDING_DIM = 768


class KnowledgeBase(Base, UUIDPrimaryKey, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "knowledge_bases"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    embedding_provider: Mapped[str] = mapped_column(String(32), default="ollama", nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(128), default="nomic-embed-text", nullable=False)
    chunk_size: Mapped[int] = mapped_column(Integer, default=1000, nullable=False)
    chunk_overlap: Mapped[int] = mapped_column(Integer, default=150, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class Document(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "documents"

    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"), index=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    source_type: Mapped[str] = mapped_column(String(16), nullable=False)  # file|url|text
    filename: Mapped[str | None] = mapped_column(String(512))
    mime_type: Mapped[str | None] = mapped_column(String(128))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    source_url: Mapped[str | None] = mapped_column(String(2048))
    status: Mapped[str] = mapped_column(String(16), default="queued", nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    storage_path: Mapped[str | None] = mapped_column(String(1024))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class Chunk(Base, UUIDPrimaryKey):
    __tablename__ = "chunks"

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"), index=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    meta: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
