"""`HybridChunker` over a persisted `DoclingDocument` (docs/14 K2-2, K2-3).

Two things this buys that the character splitter cannot.

**Chunks respect structure.** `HybridChunker` splits only what exceeds the token budget, then
merges undersized *adjacent siblings that share the same heading* (`merge_peers=True`). The
character splitter's boundaries fall wherever 1000 characters happen to land, which routinely
cuts a table in half and joins the tail of one section to the head of the next.

**Chunks are embedded with their heading path** — the highest-value, least-obvious win in
docs/14 (§3.2 W2). `contextualize()` returns:

    Returns Policy
    International Orders
    Refunds are processed within 14 days of the original purchase date.

A visitor asking *"how long for a refund on my overseas order?"* has no lexical or semantic
hook on that chunk today, because the heading was discarded at chunk time. This is precisely the
near-miss that the 0.35 score threshold then rejects, producing the no-context state that
CLAUDE.md's 2026-08-02 entry records as fabricating opening hours.

**⚠️ The enriched string is embedding input only.** `content` stays raw: it is the citation
text shown to the visitor and counted against the context budget, and repeating the heading
inside it would do both jobs worse. `tests/test_docling_chunking.py` asserts **both** directions
of that, per docs/14 §11.

## Two corrections to docs/14 §3.3, found by introspecting the installed package

1. **`DocMeta.captions` is deprecated *and* empty.** §3.3's table maps `captions → caption`.
   In the installed `docling-core`, the field is marked `deprecated=True` and the chunker leaves
   it `None` even for a table built with a caption — the caption text is inlined at the top of
   `chunk.text` instead. So it is not mapped here: reading it would emit a `DeprecationWarning`
   per chunk to populate a key that is always `None`. Nothing is lost, because the caption is in
   the chunk body and therefore in the embedding.
2. **`page` comes from `doc_items[].prov[].page_no`**, and is absent for formats with no page
   geometry (markdown, html, a programmatically built document). Omitted rather than defaulted
   to 0 — a wrong page number in a citation is worse than no page number.
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger
from app.rag.chunking import TextChunk
from app.rag.tokenizer import ENCODING_NAME, count_tokens

log = get_logger("rag.docling_chunking")


class DoclingChunkingUnavailable(RuntimeError):
    """docling-core (or its tokenizer) could not be loaded. Callers fall back to `chunk_text`."""


def _build_chunker(max_tokens: int) -> Any:
    """Construct a `HybridChunker`. Imports are local — see the module note in `converters`.

    `docling-core` pulls pandas and numpy, so importing it at module scope would put ~40 MB of
    scientific stack in the API process for a code path only the ingest worker takes.
    """
    try:
        import tiktoken
        from docling_core.transforms.chunker.hybrid_chunker import HybridChunker
        from docling_core.transforms.chunker.tokenizer.openai import OpenAITokenizer
    except Exception as exc:  # not installed, or the huggingface_hub trap (docs/14 §3.8 Trap 1)
        raise DoclingChunkingUnavailable(str(exc)) from exc

    try:
        tokenizer = OpenAITokenizer(
            tokenizer=tiktoken.get_encoding(ENCODING_NAME), max_tokens=max_tokens
        )
    except Exception as exc:  # the tiktoken download trap — see `rag.tokenizer`
        raise DoclingChunkingUnavailable(str(exc)) from exc

    # `merge_peers` is the half that fixes over-fragmentation: without it a document of short
    # paragraphs yields one chunk per paragraph, each too small to retrieve on its own.
    # `repeat_table_header` re-emits the header row on every chunk of a table that spans several,
    # so a price never arrives detached from the column it belongs to.
    return HybridChunker(tokenizer=tokenizer, merge_peers=True, repeat_table_header=True)


def _pages(chunk: Any) -> list[int]:
    pages: set[int] = set()
    for item in getattr(chunk.meta, "doc_items", None) or []:
        for prov in getattr(item, "prov", None) or []:
            page = getattr(prov, "page_no", None)
            if isinstance(page, int):
                pages.add(page)
    return sorted(pages)


def load_document(payload: dict[str, Any]) -> Any:
    """Rehydrate a `DoclingDocument` from the persisted JSON. Raises on an unusable payload."""
    try:
        from docling_core.types.doc.document import DoclingDocument
    except Exception as exc:
        raise DoclingChunkingUnavailable(str(exc)) from exc
    return DoclingDocument.model_validate(payload)


def chunk_docling_document(
    payload: dict[str, Any],
    *,
    max_tokens: int,
    metadata: dict[str, Any] | None = None,
    heading_mode: str = "embed",
) -> list[TextChunk]:
    """Chunk a persisted `DoclingDocument`.

    `heading_mode` decides where the heading path goes, and it is a **measured** choice, not a
    style preference — see docs/14 K2-5 and ADR-065:

    * ``embed`` — heading in the embedding input only, `content` raw. docs/14 §4.2's rule.
    * ``inline`` — heading prefixed to `content` as well, so the *keyword* half of hybrid
      retrieval can see it too. `content` is what the FTS index is built over, so under
      ``embed`` the heading is invisible to it.

    Raises `DoclingChunkingUnavailable` if the package or its tokenizer is missing, so the
    caller can fall back to the character splitter rather than fail the document.
    """
    chunker = _build_chunker(max_tokens)
    document = load_document(payload)

    chunks: list[TextChunk] = []
    for chunk in chunker.chunk(document):
        content = (chunk.text or "").strip()
        if not content:
            continue
        meta = dict(metadata or {})
        headings = [h for h in (getattr(chunk.meta, "headings", None) or []) if h]
        if headings:
            meta["heading"] = headings
        pages = _pages(chunk)
        if pages:
            meta["page"] = pages
        meta["chunker"] = "hybrid"
        embed_text = chunker.contextualize(chunk) or content
        if heading_mode == "inline" and embed_text != content:
            # The contextualized form *becomes* the chunk. Everything downstream — the FTS
            # index, the citation text, the context budget — then sees the heading path.
            content, embed_text = embed_text, embed_text
        chunks.append(
            TextChunk(
                ordinal=len(chunks),
                content=content,
                # Counted on what is *stored*, so the number in the knowledge UI describes the
                # text a citation will show. The embedding input is longer by the heading path.
                token_count=count_tokens(content),
                metadata=meta,
                embed_text=embed_text if embed_text != content else None,
            )
        )
    return chunks
