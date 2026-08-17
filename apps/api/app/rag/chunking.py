"""Recursive character text splitter with overlap (docs/06 §2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.rag.tokenizer import count_tokens

# Ordered separators — try to split on the most semantic boundary that fits.
_SEPARATORS = ["\n\n", "\n", ". ", " ", ""]


def estimate_tokens(text: str) -> int:
    """Token count for `text` (docs/14 K2-1).

    Was `len(text) / 4`. Now a real tokenizer, which is the same function to every caller but a
    materially different number for non-English text — see `rag.tokenizer` for why that matters
    and what it degrades to when tiktoken cannot load. The name is kept because "estimate" is
    still the honest word: it is cl100k_base's count, not the embedder's own.
    """
    return count_tokens(text)


@dataclass(slots=True)
class TextChunk:
    ordinal: int
    content: str
    token_count: int
    metadata: dict[str, Any] = field(default_factory=dict)
    #: What to send the embedding model, when that differs from what to store and cite.
    #: `None` means "embed `content`". The Docling chunker sets this to `contextualize()`'s
    #: heading-prefixed form (docs/14 §4.2) — the heading path improves the *vector* but must
    #: never be shown to a visitor or counted twice against the context budget.
    embed_text: str | None = None

    @property
    def embedding_input(self) -> str:
        return self.embed_text or self.content


def _split_recursive(text: str, size: int, seps: list[str]) -> list[str]:
    if len(text) <= size:
        return [text] if text.strip() else []
    sep = seps[0] if seps else ""
    rest = seps[1:] if len(seps) > 1 else [""]
    parts = text.split(sep) if sep else list(text)
    pieces: list[str] = []
    for part in parts:
        piece = part + sep if sep else part
        if len(piece) <= size:
            pieces.append(piece)
        else:
            pieces.extend(_split_recursive(piece, size, rest))
    return pieces


def chunk_text(
    text: str,
    chunk_size: int = 1000,
    chunk_overlap: int = 150,
    *,
    metadata: dict[str, Any] | None = None,
) -> list[TextChunk]:
    """Split `text` into overlapping chunks of at most ~`chunk_size` characters.

    `chunk_size`/`chunk_overlap` are interpreted in characters (see docs/DECISIONS ADR-021).
    """
    text = (text or "").strip()
    if not text:
        return []
    chunk_size = max(64, chunk_size)
    chunk_overlap = max(0, min(chunk_overlap, chunk_size - 1))

    pieces = _split_recursive(text, chunk_size, _SEPARATORS)

    chunks: list[TextChunk] = []
    buffer = ""
    for piece in pieces:
        if len(buffer) + len(piece) <= chunk_size:
            buffer += piece
            continue
        if buffer.strip():
            chunks.append(_emit(len(chunks), buffer, metadata))
        # Carry an overlap tail from the previous buffer into the next one.
        tail = buffer[-chunk_overlap:] if chunk_overlap else ""
        buffer = tail + piece
        while len(buffer) > chunk_size:
            head, buffer = buffer[:chunk_size], buffer[chunk_size - chunk_overlap :]
            chunks.append(_emit(len(chunks), head, metadata))
    if buffer.strip():
        chunks.append(_emit(len(chunks), buffer, metadata))
    return chunks


def _emit(ordinal: int, content: str, metadata: dict[str, Any] | None) -> TextChunk:
    content = content.strip()
    return TextChunk(
        ordinal=ordinal,
        content=content,
        token_count=estimate_tokens(content),
        metadata=dict(metadata or {}),
    )
