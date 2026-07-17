"""Knowledge-base, document, chunk, and search schemas."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from pydantic import BaseModel, Field

from app.rag.retrieval import Citation

EMBEDDING_PROVIDERS = ("ollama", "openai", "gemini", "fake")


class CreateKBRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    embedding_provider: str = Field(default="ollama", pattern="^(ollama|openai|gemini|fake)$")
    embedding_model: str = Field(default="nomic-embed-text", max_length=128)
    chunk_size: int = Field(default=1000, ge=64, le=8000)
    chunk_overlap: int = Field(default=150, ge=0, le=2000)


class UpdateKBRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    chunk_size: int | None = Field(default=None, ge=64, le=8000)
    chunk_overlap: int | None = Field(default=None, ge=0, le=2000)


class KBOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    embedding_provider: str
    embedding_model: str
    chunk_size: int
    chunk_overlap: int
    document_count: int
    created_at: dt.datetime
    updated_at: dt.datetime


class CreateDocumentRequest(BaseModel):
    """Add a document from raw text or a URL (file uploads use the /upload endpoint)."""

    source_type: str = Field(pattern="^(text|url)$")
    text: str | None = None
    url: str | None = Field(default=None, max_length=2048)
    filename: str | None = Field(default=None, max_length=512)


class DocumentOut(BaseModel):
    id: uuid.UUID
    knowledge_base_id: uuid.UUID
    source_type: str
    filename: str | None
    mime_type: str | None
    size_bytes: int | None
    source_url: str | None
    status: str
    error_message: str | None
    chunk_count: int
    created_at: dt.datetime
    updated_at: dt.datetime


class ChunkOut(BaseModel):
    id: uuid.UUID
    ordinal: int
    content: str
    token_count: int
    metadata: dict[str, Any]


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=50)
    score_threshold: float = Field(default=0.0, ge=0.0, le=1.0)
    hybrid: bool = True


class SearchResponse(BaseModel):
    query: str
    citations: list[Citation]
