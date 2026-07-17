"""Embedding providers (docs/06 §2). Free-first: Ollama `nomic-embed-text` (dim 768)."""

from __future__ import annotations

import httpx

from app.core.config import settings
from app.llm.base import ProviderError


class OllamaEmbeddingProvider:
    """Calls Ollama's batch embeddings endpoint (`/api/embed`)."""

    def __init__(
        self,
        model: str = "nomic-embed-text",
        *,
        base_url: str | None = None,
        dim: int = 768,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 60.0,
    ) -> None:
        self.model = model
        self.dim = dim
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self._transport = transport
        self._timeout = timeout

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        async with httpx.AsyncClient(
            base_url=self.base_url, timeout=self._timeout, transport=self._transport
        ) as client:
            try:
                resp = await client.post("/api/embed", json={"model": self.model, "input": texts})
            except httpx.HTTPError as exc:
                raise ProviderError(f"embedding network error: {exc}") from exc
            if resp.status_code >= 400:
                raise ProviderError(
                    f"embedding provider returned {resp.status_code}: {resp.text[:200]}",
                    retryable=resp.status_code == 429 or resp.status_code >= 500,
                )
            data = resp.json()
        vectors = data.get("embeddings") or []
        if len(vectors) != len(texts):
            raise ProviderError("embedding provider returned a mismatched vector count")
        return [[float(x) for x in v] for v in vectors]
