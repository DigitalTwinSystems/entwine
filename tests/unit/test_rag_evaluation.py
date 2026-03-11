"""Unit tests for RAG retrieval evaluation metrics."""

from __future__ import annotations

import pytest

from entwine.rag.evaluation import (
    EvalQuery,
    evaluate,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)
from entwine.rag.models import Document, SearchResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _result(doc_id: str, score: float = 0.5) -> SearchResult:
    return SearchResult(document=Document(id=doc_id, content=""), score=score)


# ---------------------------------------------------------------------------
# precision_at_k
# ---------------------------------------------------------------------------


class TestPrecisionAtK:
    def test_all_relevant(self) -> None:
        results = [_result("a"), _result("b")]
        assert precision_at_k(results, {"a", "b"}, k=2) == pytest.approx(1.0)

    def test_half_relevant(self) -> None:
        results = [_result("a"), _result("c")]
        assert precision_at_k(results, {"a", "b"}, k=2) == pytest.approx(0.5)

    def test_none_relevant(self) -> None:
        results = [_result("x"), _result("y")]
        assert precision_at_k(results, {"a"}, k=2) == pytest.approx(0.0)

    def test_empty_results(self) -> None:
        assert precision_at_k([], {"a"}, k=5) == 0.0

    def test_k_limits_results(self) -> None:
        results = [_result("a"), _result("b"), _result("c")]
        # Only look at top 1
        assert precision_at_k(results, {"a"}, k=1) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# recall_at_k
# ---------------------------------------------------------------------------


class TestRecallAtK:
    def test_all_found(self) -> None:
        results = [_result("a"), _result("b")]
        assert recall_at_k(results, {"a", "b"}, k=5) == pytest.approx(1.0)

    def test_partial_found(self) -> None:
        results = [_result("a"), _result("x")]
        assert recall_at_k(results, {"a", "b"}, k=5) == pytest.approx(0.5)

    def test_none_found(self) -> None:
        results = [_result("x")]
        assert recall_at_k(results, {"a", "b"}, k=5) == pytest.approx(0.0)

    def test_empty_relevant(self) -> None:
        results = [_result("a")]
        assert recall_at_k(results, set(), k=5) == 0.0


# ---------------------------------------------------------------------------
# reciprocal_rank
# ---------------------------------------------------------------------------


class TestReciprocalRank:
    def test_first_position(self) -> None:
        results = [_result("a"), _result("b")]
        assert reciprocal_rank(results, {"a"}) == pytest.approx(1.0)

    def test_second_position(self) -> None:
        results = [_result("x"), _result("a")]
        assert reciprocal_rank(results, {"a"}) == pytest.approx(0.5)

    def test_not_found(self) -> None:
        results = [_result("x"), _result("y")]
        assert reciprocal_rank(results, {"a"}) == 0.0


# ---------------------------------------------------------------------------
# evaluate (aggregate)
# ---------------------------------------------------------------------------


class TestEvaluate:
    def test_perfect_retrieval(self) -> None:
        queries = [
            EvalQuery(query="q1", relevant_doc_ids=["a"]),
            EvalQuery(query="q2", relevant_doc_ids=["b"]),
        ]
        results = [
            [_result("a", 0.9)],
            [_result("b", 0.8)],
        ]
        metrics = evaluate(queries, results, k=5)
        assert metrics.precision_at_k == pytest.approx(1.0)
        assert metrics.recall_at_k == pytest.approx(1.0)
        assert metrics.mrr == pytest.approx(1.0)
        assert metrics.num_queries == 2

    def test_empty_queries(self) -> None:
        metrics = evaluate([], [], k=5)
        assert metrics.num_queries == 0

    def test_mixed_quality(self) -> None:
        queries = [
            EvalQuery(query="q1", relevant_doc_ids=["a"]),
            EvalQuery(query="q2", relevant_doc_ids=["b"]),
        ]
        results = [
            [_result("a", 0.9)],  # hit
            [_result("x", 0.8)],  # miss
        ]
        metrics = evaluate(queries, results, k=5)
        assert metrics.precision_at_k == pytest.approx(0.5)
        assert metrics.recall_at_k == pytest.approx(0.5)
        assert metrics.mrr == pytest.approx(0.5)

    def test_per_query_metrics(self) -> None:
        queries = [EvalQuery(query="q1", relevant_doc_ids=["a"])]
        results = [[_result("a")]]
        metrics = evaluate(queries, results, k=5)
        assert len(metrics.per_query) == 1
        assert metrics.per_query[0]["precision"] == pytest.approx(1.0)
