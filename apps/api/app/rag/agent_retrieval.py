"""RAG retrieval driven by an agent version's ``rag_config`` (shared by playground + chat)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.llm.registry import build_embedding_provider
from app.models import AgentVersion, KnowledgeBase
from app.rag import retrieval
from app.rag.context import build_context_block
from app.rag.retrieval import Citation

log = get_logger("rag.agent")


async def retrieve_for_version(
    session: AsyncSession, org_id: uuid.UUID, version: AgentVersion, query: str
) -> tuple[str, list[Citation]]:
    """Run retrieval for a version's RAG config. Returns (context_block, citations_used)."""
    rag = version.rag_config or {}
    if not rag.get("enabled") or not rag.get("knowledge_base_ids"):
        return "", []
    try:
        kb_ids = [uuid.UUID(str(k)) for k in rag["knowledge_base_ids"]]
    except (ValueError, TypeError):
        return "", []
    stmt = select(KnowledgeBase).where(
        KnowledgeBase.organization_id == org_id,
        KnowledgeBase.id.in_(kb_ids),
        KnowledgeBase.deleted_at.is_(None),
    )
    kbs = list((await session.execute(stmt)).scalars().all())
    if not kbs:
        return "", []
    # KBs bound to one agent are expected to share an embedding model; use the first.
    embedder = build_embedding_provider(kbs[0].embedding_provider, kbs[0].embedding_model)
    try:
        citations = await retrieval.search(
            session,
            org_id,
            [kb.id for kb in kbs],
            query,
            embedder,
            top_k=int(rag.get("top_k", 5)),
            score_threshold=float(rag.get("score_threshold", 0.0)),
            hybrid=bool(rag.get("hybrid", True)),
        )
    except Exception as exc:  # retrieval failure shouldn't break the chat
        log.warning("rag_retrieval_failed", agent_version=version.version, error=str(exc))
        return "", []
    return build_context_block(citations, settings.rag_context_char_budget)
