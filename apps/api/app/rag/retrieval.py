"""Retrieval: vector top-k (+ optional hybrid full-text via RRF) with citations (docs/06 §2)."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.base import EmbeddingProvider
from app.models import Chunk

# Reciprocal-rank-fusion constant (standard default).
_RRF_K = 60


class Citation(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    knowledge_base_id: uuid.UUID
    ordinal: int
    content: str
    score: float
    metadata: dict[str, Any] = {}


def _to_citation(chunk: Chunk, score: float) -> Citation:
    return Citation(
        chunk_id=chunk.id,
        document_id=chunk.document_id,
        knowledge_base_id=chunk.knowledge_base_id,
        ordinal=chunk.ordinal,
        content=chunk.content,
        score=round(score, 6),
        metadata=chunk.meta or {},
    )


async def _vector_hits(
    session: AsyncSession,
    org_id: uuid.UUID,
    kb_ids: list[uuid.UUID],
    query_vec: list[float],
    limit: int,
) -> list[tuple[Chunk, float]]:
    distance = Chunk.embedding.cosine_distance(query_vec).label("distance")
    stmt = (
        select(Chunk, distance)
        .where(
            Chunk.organization_id == org_id,
            Chunk.knowledge_base_id.in_(kb_ids),
            Chunk.embedding.is_not(None),
        )
        .order_by(distance.asc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    # cosine similarity = 1 - cosine distance
    return [(row[0], 1.0 - float(row[1])) for row in rows]


async def _fts_hits(
    session: AsyncSession,
    org_id: uuid.UUID,
    kb_ids: list[uuid.UUID],
    query: str,
    limit: int,
) -> list[tuple[Chunk, float]]:
    tsvector = func.to_tsvector("english", Chunk.content)
    tsquery = func.plainto_tsquery("english", query)
    rank = func.ts_rank(tsvector, tsquery).label("rank")
    stmt = (
        select(Chunk, rank)
        .where(
            Chunk.organization_id == org_id,
            Chunk.knowledge_base_id.in_(kb_ids),
            tsvector.op("@@")(tsquery),
        )
        .order_by(rank.desc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    return [(row[0], float(row[1])) for row in rows]


async def search(
    session: AsyncSession,
    org_id: uuid.UUID,
    kb_ids: list[uuid.UUID],
    query: str,
    embedder: EmbeddingProvider,
    *,
    top_k: int = 5,
    score_threshold: float = 0.0,
    hybrid: bool = True,
) -> list[Citation]:
    """Return the top-k most relevant chunks for `query`, filtered by `organization_id`."""
    if not kb_ids or not query.strip():
        return []

    query_vec = (await embedder.embed([query]))[0]
    fetch = max(top_k * 4, top_k)
    vector_hits = await _vector_hits(session, org_id, kb_ids, query_vec, fetch)
    vector_hits = [(c, s) for c, s in vector_hits if s >= score_threshold]

    if not hybrid:
        return [_to_citation(c, s) for c, s in vector_hits[:top_k]]

    fts_hits = await _fts_hits(session, org_id, kb_ids, query, fetch)

    # Reciprocal rank fusion across the two ranked lists.
    fused: dict[uuid.UUID, float] = {}
    chunks: dict[uuid.UUID, Chunk] = {}
    sims: dict[uuid.UUID, float] = {}
    for rank, (chunk, sim) in enumerate(vector_hits):
        fused[chunk.id] = fused.get(chunk.id, 0.0) + 1.0 / (_RRF_K + rank + 1)
        chunks[chunk.id] = chunk
        sims[chunk.id] = sim
    for rank, (chunk, _score) in enumerate(fts_hits):
        fused[chunk.id] = fused.get(chunk.id, 0.0) + 1.0 / (_RRF_K + rank + 1)
        chunks.setdefault(chunk.id, chunk)
        sims.setdefault(chunk.id, 0.0)

    ordered = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)[:top_k]
    return [_to_citation(chunks[cid], sims[cid]) for cid, _ in ordered]
