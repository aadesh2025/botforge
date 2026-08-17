"""The eval harness's own tests (docs/13 R2, docs/14 P0-2).

Two jobs, and they are separate on purpose:

1. **The metrics are arithmetic and must be pinned to hand-computed values.** A silently wrong
   NDCG is worse than no NDCG — every phase after this one would report an improvement it did
   not earn, and the number would go into a doc and be quoted for months.
2. **The corpus must be self-consistent.** Phase D's red-team corpus failed twice on its first
   run, both times on fixtures its author had written wrong. A duplicate id silently overwrites
   a document; a qrel pointing at a renamed document makes a query permanently unanswerable and
   drags the mean down for a reason nobody can see from the output.

The full retrieval run lives in `scripts/eval_retrieval.py`, not here. It needs a populated
database and (for dense/hybrid) a real embedding provider, and burying it in 780 tests is the
"1 failed reads as flake" problem docs/11 Phase D called out.
"""

from __future__ import annotations

import json
import math

import pytest

from app.rag.evaluate import (
    DEFAULT_K,
    EvalQuery,
    EvalSetError,
    build_eval_set,
    compare,
    dcg,
    load_eval_set,
    mrr_at_k,
    ndcg_at_k,
    recall_at_k,
    score_variant,
)

# ── metrics, against values computed by hand ─────────────────────────────────────────────

def test_dcg_matches_the_formula() -> None:
    # ranks are 0-indexed, discount is log2(rank + 2): 1/1, 1/log2(3), 1/2
    assert dcg([3, 2, 1]) == pytest.approx(3 / 1 + 2 / math.log2(3) + 1 / 2)


def test_ndcg_is_one_when_the_order_is_ideal() -> None:
    assert ndcg_at_k(["a", "b"], {"a": 3, "b": 1}) == pytest.approx(1.0)


def test_ndcg_punishes_a_correct_answer_ranked_below_a_distractor() -> None:
    """The whole reason NDCG beats recall here.

    Both lists *contain* the right document. Only one of them would survive
    `build_context_block()` trimming from the bottom on a tight character budget.
    """
    good = ndcg_at_k(["right", "wrong"], {"right": 3})
    bad = ndcg_at_k(["wrong", "right"], {"right": 3})
    assert good == pytest.approx(1.0)
    assert bad == pytest.approx(1 / math.log2(3))
    assert bad < good


def test_ndcg_is_zero_when_nothing_relevant_is_returned() -> None:
    assert ndcg_at_k(["x", "y", "z"], {"a": 3}) == 0.0


def test_ndcg_respects_k() -> None:
    """A hit at rank 11 is a miss: the model is never shown it."""
    predicted = [f"filler{i}" for i in range(DEFAULT_K)] + ["right"]
    assert ndcg_at_k(predicted, {"right": 3}, k=DEFAULT_K) == 0.0
    assert ndcg_at_k(predicted, {"right": 3}, k=DEFAULT_K + 1) > 0.0


def test_ndcg_handles_a_query_with_no_relevant_documents() -> None:
    """Returns 0.0 rather than dividing by zero — one bad query must not end the run."""
    assert ndcg_at_k(["a"], {}) == 0.0
    assert ndcg_at_k(["a"], {"a": 0}) == 0.0


def test_recall_at_k() -> None:
    relevant = {"a": 3, "b": 1, "c": 1}
    assert recall_at_k(["a", "b", "z"], relevant, k=5) == pytest.approx(2 / 3)
    assert recall_at_k(["z", "y"], relevant, k=5) == 0.0
    # graded 0 is not relevant, and must not inflate the denominator
    assert recall_at_k(["a"], {"a": 3, "d": 0}, k=5) == pytest.approx(1.0)


def test_mrr_at_k() -> None:
    assert mrr_at_k(["a"], {"a": 3}) == 1.0
    assert mrr_at_k(["x", "x2", "a"], {"a": 3}) == pytest.approx(1 / 3)
    assert mrr_at_k(["x"], {"a": 3}) == 0.0


def test_a_query_with_no_prediction_scores_zero_rather_than_being_skipped() -> None:
    """Averaging over "the queries that returned something" hides the failure being measured."""
    queries = [
        EvalQuery(id="q1", text="answered", relevant={"a": 3}),
        EvalQuery(id="q2", text="returned nothing", relevant={"b": 3}),
    ]
    result = score_variant("v", {"q1": ["a"]}, queries)
    assert result.queries == 2
    assert result.ndcg == pytest.approx(0.5)
    assert result.per_query["q2"] == 0.0


# ── baseline comparison ──────────────────────────────────────────────────────────────────

def test_a_regression_beyond_tolerance_fails() -> None:
    current = score_variant("v", {"q1": ["z"]}, [EvalQuery(id="q1", text="t", relevant={"a": 3})])
    ok, message = compare(current, {"ndcg": 0.9}, tolerance=0.02)
    assert not ok
    assert "regressed" in message


def test_a_drop_inside_tolerance_passes() -> None:
    current = score_variant("v", {"q1": ["a"]}, [EvalQuery(id="q1", text="t", relevant={"a": 3})])
    ok, _ = compare(current, {"ndcg": 1.01}, tolerance=0.02)
    assert ok


def test_an_improvement_never_fails() -> None:
    current = score_variant("v", {"q1": ["a"]}, [EvalQuery(id="q1", text="t", relevant={"a": 3})])
    ok, message = compare(current, {"ndcg": 0.10}, tolerance=0.02)
    assert ok
    assert "+0.9" in message


def test_no_baseline_is_not_a_failure() -> None:
    current = score_variant("v", {}, [EvalQuery(id="q1", text="t", relevant={"a": 3})])
    ok, message = compare(current, None)
    assert ok and "no baseline" in message


# ── the frozen corpus ────────────────────────────────────────────────────────────────────

def test_the_committed_eval_set_loads_and_is_consistent() -> None:
    eval_set = load_eval_set()
    assert len(eval_set.documents) >= 30
    assert len(eval_set.queries) >= 36


def test_the_corpus_can_still_exercise_chunking() -> None:
    """Guards the blind spot K2-5 found, so it cannot come back by attrition.

    Every document in the seed corpus was 272-445 characters — one chunk at any chunk size this
    product uses — which made the corpus structurally incapable of measuring a chunking change.
    The first K2-5 run scored structural chunking *below* the baseline on a corpus where the
    mechanism it improves cannot occur, and would have rejected the phase on that basis.

    A benchmark that cannot fail in the interesting direction is not a benchmark. If someone
    later trims the long documents, this goes red instead of the corpus going quietly blind.
    """
    docs = load_eval_set().documents
    multi_chunk = [d for d in docs if len(d.text) > 1200]
    assert len(multi_chunk) >= 4, "the corpus can no longer measure a chunking change"
    assert any("## " in d.text for d in multi_chunk), "no document has internal section headings"


def test_every_query_has_a_gradeable_answer() -> None:
    """`load_eval_set` raises on an unjudged query; this asserts none slipped in as grade 0."""
    for query in load_eval_set().queries:
        assert any(g > 0 for g in query.relevant.values()), query.id


def test_the_near_miss_siblings_are_graded_zero_not_partial() -> None:
    """Serving the wrong refund window is a confidently wrong answer about someone's money.

    q001 is a domestic return and q002 an international one. If either ever picks up a nonzero
    grade for the other's document, the corpus has stopped testing the thing it was built for.
    """
    by_id = {q.id: q for q in load_eval_set().queries}
    assert by_id["q001"].relevant.get("refunds-international", 0) == 0
    assert by_id["q002"].relevant.get("refunds-domestic", 0) == 0


_DOCS = [{"id": "a", "title": "A", "text": "one"}]
_QUERIES = [{"id": "q1", "text": "t"}]
_QRELS = [{"query_id": "q1", "doc_id": "a", "relevance": 3}]


def test_the_corpus_rejects_a_duplicate_id() -> None:
    """The check that caught two of this author's own mistakes in Phase D. Keep it."""
    with pytest.raises(EvalSetError, match="duplicate document ids"):
        build_eval_set([*_DOCS, {"id": "a", "title": "A2", "text": "two"}], _QUERIES, _QRELS)


def test_the_corpus_rejects_a_duplicate_query_id() -> None:
    with pytest.raises(EvalSetError, match="duplicate query ids"):
        build_eval_set(_DOCS, [*_QUERIES, {"id": "q1", "text": "u"}], _QRELS)


def test_the_corpus_rejects_a_qrel_pointing_at_a_renamed_document() -> None:
    with pytest.raises(EvalSetError, match="unknown document"):
        build_eval_set(_DOCS, _QUERIES, [{"query_id": "q1", "doc_id": "gone", "relevance": 3}])


def test_the_corpus_rejects_a_qrel_for_a_query_that_does_not_exist() -> None:
    with pytest.raises(EvalSetError, match="unknown query"):
        build_eval_set(_DOCS, _QUERIES, [{"query_id": "q9", "doc_id": "a", "relevance": 3}])


def test_the_corpus_rejects_a_query_nothing_answers() -> None:
    """Otherwise it scores a legitimate-looking 0.0 forever and drags the mean down invisibly."""
    with pytest.raises(EvalSetError, match="no relevant document"):
        build_eval_set(_DOCS, [*_QUERIES, {"id": "q2", "text": "u"}], _QRELS)


# ── the committed baseline ───────────────────────────────────────────────────────────────

def test_the_baseline_is_keyed_by_embedder() -> None:
    """A fake-embedder number and a real one must never be comparable by accident.

    `FakeEmbeddingProvider` hashes text, so a 'dense' score under it measures a hash function.
    Keying the baseline by embedder is what stops the two being read off the same row.
    """
    from app.rag.evaluate import EVAL_SET_DIR

    baseline = json.loads((EVAL_SET_DIR / "baseline.json").read_text(encoding="utf-8"))
    runs = baseline["runs"]
    assert "fake" in runs
    assert set(runs["fake"]) == {"fts"}, "the fake embedder can only score the keyword half"
    assert any(key != "fake" for key in runs), "no real-embedder baseline has been recorded"
