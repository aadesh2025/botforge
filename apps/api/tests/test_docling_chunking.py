"""Structural chunking and real token counts (docs/14 K2-1, K2-2, K2-3).

docs/14 §11 names the assertion this file exists to make:

> **Assert both directions of `contextualize()`** — stored `content` clean, embedding input
> enriched.

Testing only one direction is how a feature ships inverted. Phase B's PII allowlist passed for
weeks while doing the opposite of its purpose, because every test asserted the direction that
also passes when the feature is broken. A test that checks only "the embedding input has the
heading" goes green if `content` has it too — which would put the heading in front of every
visitor, twice in the context budget.

These build a real `DoclingDocument` in-process. No test may call docling-serve.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.rag import tokenizer
from app.rag.chunking import TextChunk, chunk_text, estimate_tokens
from app.rag.docling_chunking import DoclingChunkingUnavailable, chunk_docling_document

docling_core = pytest.importorskip("docling_core", reason="docling-core is an optional extra")

HEADING_1 = "Returns Policy"
HEADING_2 = "International Orders"
BODY = "Refunds are processed within 14 days of the original purchase date."
SIBLING = "Shipping outside India takes 10-15 business days."
OTHER_BODY = "Domestic refunds land in 3 days."


def _document() -> dict[str, Any]:
    """A two-section document, as `DoclingDocument` JSON — the shape K1 persists."""
    from docling_core.types.doc.document import DoclingDocument
    from docling_core.types.doc.labels import DocItemLabel

    doc = DoclingDocument(name="policy")
    top = doc.add_heading(text=HEADING_1, level=1)
    intl = doc.add_heading(text=HEADING_2, level=2, parent=top)
    doc.add_text(label=DocItemLabel.TEXT, text=BODY, parent=intl)
    doc.add_text(label=DocItemLabel.TEXT, text=SIBLING, parent=intl)
    dom = doc.add_heading(text="Domestic Orders", level=2, parent=top)
    doc.add_text(label=DocItemLabel.TEXT, text=OTHER_BODY, parent=dom)
    return doc.model_dump(mode="json")


def _chunks() -> list[TextChunk]:
    return chunk_docling_document(_document(), max_tokens=512, metadata={"filename": "policy.pdf"})


# ── K2-3: both directions, which is the whole point ──────────────────────────────────────

def test_the_heading_path_is_embedded() -> None:
    chunks = _chunks()
    target = next(c for c in chunks if BODY in c.content)
    assert HEADING_1 in target.embedding_input
    assert HEADING_2 in target.embedding_input
    assert BODY in target.embedding_input


def test_the_heading_path_is_not_stored() -> None:
    """The other direction. `content` is the citation text a visitor reads."""
    chunks = _chunks()
    target = next(c for c in chunks if BODY in c.content)
    assert HEADING_1 not in target.content
    assert HEADING_2 not in target.content
    assert target.content.strip() != target.embedding_input.strip()


def test_the_enriched_string_is_never_persisted_as_content() -> None:
    """Belt and braces across every chunk, not just the one under inspection."""
    for chunk in _chunks():
        assert not chunk.content.startswith(HEADING_1)


def test_inline_mode_puts_the_heading_where_the_fts_index_can_see_it() -> None:
    """ADR-065. The FTS index is built over `chunks.content`, so under the default `embed` mode
    the heading path is invisible to the keyword half of hybrid retrieval — measured as an
    NDCG@10 drop in docs/14's K2-5 table, not reasoned about. `inline` is the opposite trade."""
    chunks = chunk_docling_document(_document(), max_tokens=512, heading_mode="inline")
    target = next(c for c in chunks if BODY in c.content)
    assert target.content.startswith(HEADING_1)
    assert HEADING_2 in target.content
    # And the embedding input still carries it, so `inline` adds signal rather than moving it.
    assert HEADING_1 in target.embedding_input


def test_the_two_heading_modes_really_differ() -> None:
    """Both directions on the same input. A mode flag that changes nothing is worse than none."""
    payload = _document()
    embed = chunk_docling_document(payload, max_tokens=512, heading_mode="embed")
    inline = chunk_docling_document(payload, max_tokens=512, heading_mode="inline")
    assert [c.content for c in embed] != [c.content for c in inline]
    assert [c.embedding_input for c in embed] == [c.embedding_input for c in inline]


# ── K2-2: structure lands in metadata ────────────────────────────────────────────────────

def test_every_chunk_carries_its_heading_path() -> None:
    chunks = _chunks()
    assert chunks
    for chunk in chunks:
        assert chunk.metadata["heading"], chunk.content
    target = next(c for c in chunks if BODY in c.content)
    assert target.metadata["heading"] == [HEADING_1, HEADING_2]


def test_caller_metadata_survives() -> None:
    assert all(c.metadata["filename"] == "policy.pdf" for c in _chunks())


def test_peers_under_one_heading_merge_and_other_sections_do_not() -> None:
    """`merge_peers=True`. Two short paragraphs under one heading are one retrievable chunk;
    a paragraph under a different heading stays separate, or the heading path would be a lie."""
    chunks = _chunks()
    target = next(c for c in chunks if BODY in c.content)
    assert SIBLING in target.content
    assert OTHER_BODY not in target.content


def test_no_page_key_when_the_document_has_no_page_geometry() -> None:
    """A wrong page number in a citation is worse than no page number."""
    assert all("page" not in c.metadata for c in _chunks())


# ── K2-1: real tokens ────────────────────────────────────────────────────────────────────

def test_token_count_is_the_tokenizers_not_a_character_ratio() -> None:
    text = "unbelievably internationalization"
    assert estimate_tokens(text) != max(1, round(len(text) / 4))


def test_token_count_of_a_known_fixture() -> None:
    """cl100k_base, pinned. If this moves, every stored `token_count` has silently re-scaled."""
    assert estimate_tokens("hello world") == 2
    assert estimate_tokens("") == 0


def test_non_english_is_no_longer_wildly_undercounted() -> None:
    """The reason this replaced `len/4` (docs/14 K2-1, docs/11 §9.2a).

    `len/4` assumes ~4 characters per token, which holds for English and collapses for Tamil —
    where cl100k_base spends several tokens on a single word. Under the old heuristic a Tamil
    chunk was reported at a fraction of its real size, so every budget computed from it was
    optimistic for exactly the clients least well served elsewhere in the stack.
    """
    tamil = "எங்கள் கொள்கைகள் பற்றிய தகவல்கள் இங்கே உள்ளன."
    assert estimate_tokens(tamil) > max(1, round(len(tamil) / 4)) * 2


def test_counting_degrades_instead_of_raising_when_tiktoken_is_gone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A counter must never be able to fail an ingest.

    A worker with no network cannot download the BPE ranks, and a document turning to
    `status=failed` because a *reporting field* could not initialise would be absurd.
    """
    tokenizer.reset_for_tests()
    monkeypatch.setattr(tokenizer, "get_encoder", lambda: None)
    try:
        assert tokenizer.count_tokens("abcd") == 1
        assert tokenizer.count_tokens("a" * 400) == 100
        assert tokenizer.count_tokens("") == 0
    finally:
        tokenizer.reset_for_tests()


# ── the fallback, per docs/14 §11 ────────────────────────────────────────────────────────

def test_an_unusable_payload_raises_so_the_caller_can_fall_back() -> None:
    # pydantic's ValidationError is a ValueError; a missing package is the other named case.
    with pytest.raises((DoclingChunkingUnavailable, ValueError)):
        chunk_docling_document({"not": "a docling document"}, max_tokens=512)


def test_the_character_splitter_still_works_unchanged() -> None:
    """The legacy path is still the majority of documents and is not allowed to regress."""
    chunks = chunk_text("A. " * 400, chunk_size=200, chunk_overlap=20)
    assert len(chunks) > 1
    assert all(c.token_count > 0 for c in chunks)
    assert all(c.embed_text is None for c in chunks)
    assert all(c.embedding_input == c.content for c in chunks)


def test_unavailable_is_an_exception_the_caller_can_name() -> None:
    assert issubclass(DoclingChunkingUnavailable, RuntimeError)
