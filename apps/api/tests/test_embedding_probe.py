"""docs/15 PROD-2 — the startup check that names an unreachable embedding provider.

Production passed `OLLAMA_BASE_URL=http://ollama:11434` while the prod compose declared no such
service. Every embed call failed, every document ingest failed, and nothing in the configuration
looked wrong — the same shape as the `.env`-comment-as-API-key outage (ADR-044).

Two properties matter more than the log text, and both are asserted here:

1. **The probe never raises and never blocks startup.** A diagnostic that can stop the API coming
   up is worse than the bug it reports.
2. **An endpoint that answers is not the same as embeddings working.** `ollama/ollama` starts with
   no models, so a healthy port with an unpulled model is still broken — which is precisely how a
   "fixed" PROD-2 could still fail on the first client upload.
"""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest

from app.core.config import settings
from app.llm import embeddings


@pytest.fixture(autouse=True)
def _probe_on() -> Iterator[None]:
    """conftest disables the probe for the suite; this file is where it is exercised."""
    previous = settings.embedding_probe_enabled
    settings.embedding_probe_enabled = True
    yield
    settings.embedding_probe_enabled = previous


@pytest.fixture
def _ollama_config() -> Iterator[None]:
    original = (settings.embedding_provider, settings.embedding_model, settings.ollama_base_url)
    settings.embedding_provider = "ollama"
    settings.embedding_model = "nomic-embed-text"
    settings.ollama_base_url = "http://ollama:11434"
    yield
    settings.embedding_provider, settings.embedding_model, settings.ollama_base_url = original


def _tags(*names: str) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/tags"
        return httpx.Response(200, json={"models": [{"name": n} for n in names]})

    return httpx.MockTransport(handler)


# ── the failure the check exists for ─────────────────────────────────────────────────────────

async def test_an_unreachable_endpoint_is_reported_not_raised(_ollama_config: None) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("nodename nor servname provided", request=request)

    ok, reason = await embeddings.probe_reachable(transport=httpx.MockTransport(handler))
    assert ok is False
    assert reason is not None and "ConnectError" in reason


async def test_a_healthy_endpoint_without_the_model_is_still_a_failure(
    _ollama_config: None,
) -> None:
    """The half of PROD-2 that adding an `ollama` service does NOT fix.

    `ollama/ollama` serves an API with no models. Embedding against a model it has not pulled is
    an error, not an implicit download — so "the port answers" is not evidence that anything
    works, and a compose fix that stops at `image: ollama/ollama` is still broken.
    """
    ok, reason = await embeddings.probe_reachable(transport=_tags("qwen3:14b"))
    assert ok is False
    assert reason == "model nomic-embed-text:latest not pulled"


async def test_an_http_error_is_reported(_ollama_config: None) -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(503, text="unavailable"))
    ok, reason = await embeddings.probe_reachable(transport=transport)
    assert ok is False
    assert reason == "HTTP 503"


# ── and the cases that must stay quiet ───────────────────────────────────────────────────────

@pytest.mark.parametrize("listed", ["nomic-embed-text", "nomic-embed-text:latest"])
async def test_an_untagged_and_a_latest_tagged_model_both_count(
    _ollama_config: None, listed: str
) -> None:
    """Ollama reports `name: "nomic-embed-text:latest"` for a model configured untagged.

    Comparing the strings raw would report a correctly-provisioned deployment as broken, which
    trains an operator to ignore the one message that matters.
    """
    ok, reason = await embeddings.probe_reachable(transport=_tags(listed))
    assert (ok, reason) == (True, None)


async def test_a_disabled_probe_makes_no_request(_ollama_config: None) -> None:
    settings.embedding_probe_enabled = False

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - must not run
        raise AssertionError("the probe made a request while disabled")

    assert await embeddings.probe_reachable(transport=httpx.MockTransport(handler)) == (True, None)


async def test_force_fake_makes_no_request(_ollama_config: None) -> None:
    """`LLM_FORCE_FAKE` replaces the embedder outright, so the real endpoint is irrelevant."""
    previous = settings.llm_force_fake
    settings.llm_force_fake = True
    try:

        def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
            raise AssertionError("the probe made a request under LLM_FORCE_FAKE")

        result = await embeddings.probe_reachable(transport=httpx.MockTransport(handler))
    finally:
        settings.llm_force_fake = previous
    assert result == (True, None)


async def test_a_non_ollama_provider_is_not_probed(_ollama_config: None) -> None:
    settings.embedding_provider = "fake"

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("probed an endpoint the configured provider does not use")

    assert await embeddings.probe_reachable(transport=httpx.MockTransport(handler)) == (True, None)


async def test_an_unexpected_200_body_does_not_report_a_failure(_ollama_config: None) -> None:
    """Something is serving there. The embed call will give a precise error; don't guess."""
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text="not json"))
    assert await embeddings.probe_reachable(transport=transport) == (True, None)


# ── the configuration-only half ──────────────────────────────────────────────────────────────

def test_openai_and_gemini_are_flagged_as_having_no_adapter() -> None:
    """`build_embedding_provider` accepts them and constructs an Ollama client anyway.

    An operator setting `EMBEDDING_PROVIDER=openai` to escape a missing Ollama would change
    nothing whatsoever, and there is no symptom that distinguishes it from having worked. Pinned
    here so that if an adapter is ever written, this test fails and the warning gets removed.
    """
    from app.llm.registry import build_embedding_provider

    for name in ("openai", "gemini"):
        assert isinstance(
            build_embedding_provider(name, "text-embedding-3-small"),
            embeddings.OllamaEmbeddingProvider,
        )
        assert name in embeddings.OLLAMA_ROUTED


def test_the_known_provider_list_matches_what_the_factory_accepts() -> None:
    """`KNOWN_PROVIDERS` drives the startup warning, so it must not drift from the factory."""
    from app.core.errors import AppError
    from app.llm.registry import build_embedding_provider

    for name in embeddings.KNOWN_PROVIDERS:
        assert build_embedding_provider(name, "nomic-embed-text") is not None
    with pytest.raises(AppError):
        build_embedding_provider("cohere", "embed-english-v3.0")
