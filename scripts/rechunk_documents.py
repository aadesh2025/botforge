#!/usr/bin/env python
"""Re-chunk and re-embed documents from their persisted `DoclingDocument` (docs/14 K2-4).

    cd apps/api && ./.venv/Scripts/python.exe ../../scripts/rechunk_documents.py
    cd apps/api && ./.venv/Scripts/python.exe ../../scripts/rechunk_documents.py --org acme --apply
    make rechunk

**This is the payoff for persisting the JSON in K1.** Conversion is the expensive half — layout
analysis, OCR, table structure — and it is already done. Re-chunking reads that stored document
back, so changing the chunk budget or the chunker itself costs an embedding pass instead of a
full re-conversion of every document in every org. It is what makes chunking a parameter the
eval harness can sweep rather than a one-shot commitment.

**Dry-run by default**, like every other operational script here. `--apply` is the flag that
writes.

## Resumability, and why it needs no bookkeeping table

Each document is committed on its own. A document that has already been re-chunked is
recognisable from its own chunks — `metadata.chunker == "hybrid"` — so an interrupted run is
resumed by simply running it again: finished documents are skipped, the one that was in flight
was never committed, and the rest proceed. `--force` re-does everything, which is what you want
after changing `DOCLING_CHUNK_MAX_TOKENS`.

## What it deliberately does not do

- **It does not convert.** A document with no `docling_json_path` is skipped and counted, never
  sent to docling-serve. Re-conversion is a different, far more expensive job with a different
  failure mode, and quietly folding it in here would make a "re-chunk" run unbounded in cost.
- **It does not touch `documents.status`.** A document that is `ready` stays `ready` throughout;
  chunks are replaced inside one transaction so retrieval never observes a document with none.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings
from app.llm.registry import build_embedding_provider
from app.models import Chunk, Document, KnowledgeBase, Organization
from app.rag.docling_chunking import DoclingChunkingUnavailable, chunk_docling_document

_EMBED_BATCH = 64


async def _already_rechunked(session: AsyncSession, document_id: object) -> bool:
    row = (
        await session.execute(
            select(Chunk.meta).where(Chunk.document_id == document_id).order_by(Chunk.ordinal).limit(1)
        )
    ).scalar_one_or_none()
    return bool(row) and row.get("chunker") == "hybrid"


def _load_payload(storage_path: str) -> dict | None:
    """Read the persisted DoclingDocument. Sync, so the blocking read is honest (ruff ASYNC240)."""
    path = Path(storage_path)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


async def _rechunk_one(
    session: AsyncSession, document: Document, kb: KnowledgeBase, *, apply: bool
) -> tuple[str, int]:
    """Returns (outcome, chunk_count). Never raises for a single bad document."""
    if not document.docling_json_path:
        return "no-structure", 0
    try:
        payload = _load_payload(document.docling_json_path)
    except (OSError, ValueError):
        return "json-unreadable", 0
    if payload is None:
        # The row points at a file that is gone. Worth reporting rather than silently skipping:
        # it means a re-chunk of this document does need a re-conversion after all.
        return "json-missing", 0

    try:
        chunks = chunk_docling_document(
            payload,
            max_tokens=settings.docling_chunk_max_tokens,
            metadata={
                "filename": document.filename,
                "source_url": document.source_url,
                "backend": document.extraction_backend,
            },
        )
    except DoclingChunkingUnavailable:
        raise  # a missing package is a run-wide problem, not a per-document one
    except Exception:
        return "chunk-failed", 0

    if not chunks:
        # Replacing real chunks with nothing would delete a client's retrievable content.
        return "empty", 0
    if not apply:
        return "would-rechunk", len(chunks)

    embedder = build_embedding_provider(kb.embedding_provider, kb.embedding_model)
    vectors: list[list[float]] = []
    for i in range(0, len(chunks), _EMBED_BATCH):
        batch = [c.embedding_input for c in chunks[i : i + _EMBED_BATCH]]
        vectors.extend(await embedder.embed(batch))

    await session.execute(delete(Chunk).where(Chunk.document_id == document.id))
    for chunk, vector in zip(chunks, vectors, strict=True):
        session.add(
            Chunk(
                document_id=document.id,
                knowledge_base_id=document.knowledge_base_id,
                organization_id=document.organization_id,
                ordinal=chunk.ordinal,
                content=chunk.content,
                token_count=chunk.token_count,
                meta=chunk.metadata,
                embedding=vector,
            )
        )
    document.chunk_count = len(chunks)
    await session.commit()  # per document, so an interrupted run resumes cleanly
    return "rechunked", len(chunks)


async def run(*, org_slug: str | None, apply: bool, force: bool, limit: int | None) -> int:
    engine = create_async_engine(settings.database_url)
    counts: dict[str, int] = {}
    total_chunks = 0
    processed = 0

    async with AsyncSession(engine) as session:
        query = select(Document, KnowledgeBase).join(
            KnowledgeBase, KnowledgeBase.id == Document.knowledge_base_id
        )
        if org_slug:
            org = (
                await session.execute(select(Organization).where(Organization.slug == org_slug))
            ).scalar_one_or_none()
            if org is None:
                print(f"No organization with slug {org_slug!r}.")
                return 1
            query = query.where(Document.organization_id == org.id)
        query = query.where(Document.docling_json_path.is_not(None)).order_by(Document.id)

        rows = (await session.execute(query)).all()
        for document, kb in rows:
            if limit is not None and processed >= limit:
                break
            if not force and await _already_rechunked(session, document.id):
                counts["skipped-done"] = counts.get("skipped-done", 0) + 1
                continue
            outcome, n = await _rechunk_one(session, document, kb, apply=apply)
            counts[outcome] = counts.get(outcome, 0) + 1
            total_chunks += n
            processed += 1
            name = document.filename or document.source_url or str(document.id)
            print(f"  {outcome:<14} {name[:60]:<62} {n or '':>4}")

    await engine.dispose()

    print(f"\n{len(rows)} document(s) with a persisted DoclingDocument.")
    for outcome in sorted(counts):
        print(f"  {outcome:<14} {counts[outcome]}")
    print(f"  {'chunks':<14} {total_chunks}")
    if not apply:
        print("\nDry run - nothing was written. Re-run with --apply.\n")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("--org", dest="org_slug", help="restrict to one organization slug")
    parser.add_argument("--apply", action="store_true", help="write (default is a dry run)")
    parser.add_argument(
        "--force",
        action="store_true",
        help="re-chunk documents already chunked by the hybrid chunker (after a budget change)",
    )
    parser.add_argument("--limit", type=int, help="stop after N documents")
    args = parser.parse_args()
    return asyncio.run(
        run(org_slug=args.org_slug, apply=args.apply, force=args.force, limit=args.limit)
    )


if __name__ == "__main__":
    raise SystemExit(main())
