"""Stage 4 — the cross-encoder reranker (docs/13 R1, docs/14 K4).

The rules this file exists to hold, all of which come from something this repo has already been
bitten by:

* **The no-op must be byte-identical to no reranker at all.** Enabling reranking has to be a
  decision, never a side effect of the code landing.
* **It fails open, to the ordering we already had.** Every guard layer in docs/11 fails open;
  a rerank outage that returned an empty result set would give the agent no context and put it
  straight back on the fabrication path (docs/11 §9).
* **A failure and a no-change are different states.** `apply()` returns `None` for "did not
  run", exactly as `score_injection()` does. A caller that reads one as the other is the bug.
* **The credential is the platform's.** ADR-055 established this for guard models after working
  out that `resolve_credential()`'s agent -> org -> env chain would resolve a client's own key
  against someone else's endpoint, silently, because the layer fails open.

No test may call a real rerank service. `conftest.py` leaves `rerank_enabled` off for the whole
suite; the tests here turn it on with a mock transport, the same shape `test_guard_models.py`
uses for L2.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.core.config import settings
from app.rag import rerank
from app.rag.rerank import HttpCrossEncoderReranker, NoOpReranker


def _transport(handler) -> httpx.MockTransport:  # type: ignore[no-untyped-def]
    return httpx.MockTransport(handler)


def _scores(*pairs: tuple[int, float]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[{"index": i, "score": s} for i, s in pairs])

    return _transport(handler)


# ── the no-op default ────────────────────────────────────────────────────────────────────

async def test_the_noop_preserves_order_exactly() -> None:
    result = await NoOpReranker().rerank("q", ["a", "b", "c"])
    assert [i for i, _ in result] == [0, 1, 2]


async def test_apply_returns_none_for_the_noop() -> None:
    """`None` is "did not run". A caller must fall back to the order it already had."""
    assert await rerank.apply(NoOpReranker(), "q", ["a", "b"]) is None


async def test_build_reranker_is_a_noop_unless_both_switches_are_set() -> None:
    previous = (settings.rerank_enabled, settings.rerank_endpoint)
    try:
        settings.rerank_enabled = False
        settings.rerank_endpoint = "http://rerank:8080"
        assert isinstance(rerank.build_reranker(), NoOpReranker)

        # Enabled but with nowhere to call is the dangerous state, not the harmless one: every
        # agent with reranking on silently gets RRF ordering, which looks exactly like a
        # reranker that ran and agreed. It degrades safely here and warns at startup.
        settings.rerank_enabled = True
        settings.rerank_endpoint = ""
        assert isinstance(rerank.build_reranker(), NoOpReranker)
        assert "RERANK_ENDPOINT is empty" in (rerank.unavailable_reason() or "")

        settings.rerank_endpoint = "http://rerank:8080"
        assert isinstance(rerank.build_reranker(), HttpCrossEncoderReranker)
        assert rerank.unavailable_reason() is None
    finally:
        settings.rerank_enabled, settings.rerank_endpoint = previous


# ── the HTTP client ──────────────────────────────────────────────────────────────────────

async def test_it_reorders_by_score_descending() -> None:
    reranker = HttpCrossEncoderReranker(
        "http://rerank:8080", transport=_scores((0, 0.1), (1, 0.9), (2, 0.5))
    )
    assert await rerank.apply(reranker, "q", ["a", "b", "c"]) == [1, 2, 0]


async def test_it_sends_the_query_and_the_texts() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("Authorization")
        return httpx.Response(200, json=[{"index": 0, "score": 1.0}])

    reranker = HttpCrossEncoderReranker(
        "http://rerank:8080/", model="BAAI/bge-reranker-v2-m3", api_key="k", transport=_transport(handler)
    )
    await reranker.rerank("how long for a refund", ["doc one"])
    assert seen["query"] == "how long for a refund"
    assert seen["texts"] == ["doc one"]
    assert seen["model"] == "BAAI/bge-reranker-v2-m3"
    assert seen["url"] == "http://rerank:8080/rerank"
    assert seen["auth"] == "Bearer k"


async def test_it_reads_the_hosted_response_shape_too() -> None:
    """TEI answers with a bare list of `{index, score}`; hosted APIs wrap and rename both."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [
                    {"document": {"index": 2}, "relevance_score": 0.8},
                    {"document": {"index": 0}, "relevance_score": 0.2},
                ]
            },
        )

    reranker = HttpCrossEncoderReranker("http://rerank:8080", transport=_transport(handler))
    assert await rerank.apply(reranker, "q", ["a", "b", "c"]) == [2, 0]


# ── failing open ─────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "handler",
    [
        pytest.param(lambda r: httpx.Response(500, text="boom"), id="upstream_error"),
        pytest.param(lambda r: httpx.Response(200, json={"unexpected": True}), id="bad_shape"),
        pytest.param(lambda r: httpx.Response(200, json=[{"score": 0.5}]), id="missing_index"),
        pytest.param(lambda r: httpx.Response(200, text="not json"), id="not_json"),
    ],
)
async def test_every_failure_degrades_to_the_existing_order(handler) -> None:  # type: ignore[no-untyped-def]
    reranker = HttpCrossEncoderReranker("http://rerank:8080", transport=_transport(handler))
    assert await rerank.apply(reranker, "q", ["a", "b", "c"]) is None


async def test_a_timeout_degrades_to_the_existing_order() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("too slow", request=request)

    reranker = HttpCrossEncoderReranker("http://rerank:8080", transport=_transport(handler))
    assert await rerank.apply(reranker, "q", ["a", "b"]) is None


async def test_an_out_of_range_index_is_rejected_rather_than_applied() -> None:
    """Trusting it would silently reorder the caller's list into something unrelated.

    The caller indexes its own candidate list with whatever comes back, so an index of 9 for a
    3-document request is not a ranking error — it is an IndexError on a visitor's turn, or
    worse, a citation pointing at the wrong chunk.
    """
    reranker = HttpCrossEncoderReranker("http://rerank:8080", transport=_scores((9, 0.9)))
    assert await rerank.apply(reranker, "q", ["a", "b", "c"]) is None


async def test_no_documents_is_not_a_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - must not run
        raise AssertionError("reranking an empty candidate list must not hit the network")

    reranker = HttpCrossEncoderReranker("http://rerank:8080", transport=_transport(handler))
    assert await rerank.apply(reranker, "q", []) is None


# ── whose key pays ───────────────────────────────────────────────────────────────────────

def test_the_key_is_the_platforms_and_nothing_else() -> None:
    """ADR-055's rule, restated as ADR-063.

    `resolve_credential()` walks agent -> org -> env and falls back to the env key *last*, so an
    org holding its own Mistral or DeepSeek key would have had that key sent to the rerank
    endpoint. Because this layer fails open, nothing would have said so.
    """
    # Asserted on the module's namespace, not its text — the docstring names the function it is
    # deliberately not using, and a grep over the source would fail on the explanation.
    assert not hasattr(rerank, "resolve_credential")
    assert "app.llm.registry" not in {
        getattr(v, "__module__", "") for v in vars(rerank).values()
    }
    previous = settings.rerank_api_key
    try:
        settings.rerank_api_key = "  "
        assert rerank.platform_rerank_key() is None  # blank is unset, per ADR-020
        settings.rerank_api_key = "platform-key"
        assert rerank.platform_rerank_key() == "platform-key"
    finally:
        settings.rerank_api_key = previous
