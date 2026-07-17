"""Phase 7 unit tests: chunking, loaders, and context assembly (no DB / no network)."""

from __future__ import annotations

import uuid

from app.llm.fake import FakeEmbeddingProvider
from app.rag.chunking import chunk_text, estimate_tokens
from app.rag.context import build_context_block
from app.rag.loaders import load_bytes, load_csv, strip_html
from app.rag.retrieval import Citation


def test_estimate_tokens() -> None:
    assert estimate_tokens("") == 0
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("a" * 400) == 100


def test_chunk_text_splits_with_overlap() -> None:
    text = " ".join(f"word{i}" for i in range(400))
    chunks = chunk_text(text, chunk_size=200, chunk_overlap=40)
    assert len(chunks) > 1
    assert all(len(c.content) <= 200 for c in chunks)
    assert [c.ordinal for c in chunks] == list(range(len(chunks)))
    assert all(c.token_count > 0 for c in chunks)


def test_chunk_text_empty() -> None:
    assert chunk_text("   ") == []


def test_chunk_text_short_single() -> None:
    chunks = chunk_text("hello world", chunk_size=1000, chunk_overlap=100)
    assert len(chunks) == 1
    assert chunks[0].content == "hello world"


def test_strip_html() -> None:
    html = "<html><head><style>x{}</style></head><body><h1>Hi</h1><p>There <b>bold</b></p></body></html>"
    text = strip_html(html)
    assert "Hi" in text and "There" in text and "bold" in text
    assert "<" not in text and "x{}" not in text


def test_load_csv() -> None:
    data = b"name,city\nAda,London\nGrace,NYC\n"
    out = load_csv(data)
    assert "name: Ada" in out and "city: London" in out
    assert "Grace" in out


def test_load_bytes_text() -> None:
    assert load_bytes(b"plain text here", filename="notes.txt", mime_type="text/plain") == "plain text here"


async def test_fake_embedder_matches_kb_dim() -> None:
    emb = FakeEmbeddingProvider(dim=768)
    out = await emb.embed(["a", "b"])
    assert len(out) == 2 and len(out[0]) == 768


def test_build_context_block_budget() -> None:
    cites = [
        Citation(
            chunk_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            knowledge_base_id=uuid.uuid4(),
            ordinal=i,
            content="X" * 100,
            score=1.0 - i * 0.1,
            metadata={"filename": "doc.txt"},
        )
        for i in range(5)
    ]
    block, used = build_context_block(cites, char_budget=250)
    assert 0 < len(used) < 5  # budget trims lower-ranked citations
    assert "doc.txt" in block
    assert "[1]" in block


def test_build_context_block_empty() -> None:
    assert build_context_block([], char_budget=1000) == ("", [])
