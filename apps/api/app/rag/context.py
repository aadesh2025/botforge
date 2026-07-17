"""Assemble a retrieved-context block for the prompt, within a character/token budget."""

from __future__ import annotations

from app.rag.retrieval import Citation


def build_context_block(citations: list[Citation], char_budget: int) -> tuple[str, list[Citation]]:
    """Render citations into a source-marked context block, trimmed to `char_budget`.

    Returns the block text and the subset of citations that actually fit (so the caller only
    advertises sources the model was given). Citations keep their input ordering (most relevant
    first); lower-ranked ones are dropped first when the budget is tight.
    """
    if not citations or char_budget <= 0:
        return "", []

    used: list[Citation] = []
    parts: list[str] = []
    total = 0
    for i, cite in enumerate(citations, start=1):
        source = cite.metadata.get("filename") or cite.metadata.get("source_url") or "document"
        block = f"[{i}] (source: {source})\n{cite.content}".strip()
        if used and total + len(block) + 2 > char_budget:
            break
        parts.append(block)
        used.append(cite)
        total += len(block) + 2

    if not used:
        return "", []
    header = "Use the following retrieved context to answer. Cite sources as [n] when relevant.\n\n"
    return header + "\n\n".join(parts), used
