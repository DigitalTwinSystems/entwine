"""Retrieval quality evaluation: Precision@k, Recall@k, MRR."""

from __future__ import annotations

from dataclasses import dataclass, field

from entwine.rag.models import SearchResult


@dataclass
class EvalQuery:
    """A single evaluation query with expected relevant document IDs."""

    query: str
    relevant_doc_ids: list[str]
    role: str = "company-wide"


@dataclass
class EvalMetrics:
    """Aggregated retrieval quality metrics."""

    precision_at_k: float = 0.0
    recall_at_k: float = 0.0
    mrr: float = 0.0
    num_queries: int = 0
    per_query: list[dict[str, float]] = field(default_factory=list)


def precision_at_k(results: list[SearchResult], relevant_ids: set[str], k: int = 5) -> float:
    """Fraction of top-k results that are relevant."""
    top_k = results[:k]
    if not top_k:
        return 0.0
    hits = sum(1 for r in top_k if r.document.id in relevant_ids)
    return hits / len(top_k)


def recall_at_k(results: list[SearchResult], relevant_ids: set[str], k: int = 5) -> float:
    """Fraction of relevant docs found in top-k results."""
    if not relevant_ids:
        return 0.0
    top_k = results[:k]
    hits = sum(1 for r in top_k if r.document.id in relevant_ids)
    return hits / len(relevant_ids)


def reciprocal_rank(results: list[SearchResult], relevant_ids: set[str]) -> float:
    """Reciprocal rank of the first relevant result."""
    for i, r in enumerate(results, start=1):
        if r.document.id in relevant_ids:
            return 1.0 / i
    return 0.0


def evaluate(
    queries: list[EvalQuery],
    results_per_query: list[list[SearchResult]],
    k: int = 5,
) -> EvalMetrics:
    """Compute aggregate P@k, R@k, and MRR over a set of queries."""
    if not queries:
        return EvalMetrics()

    total_p = 0.0
    total_r = 0.0
    total_rr = 0.0
    per_query: list[dict[str, float]] = []

    for query, results in zip(queries, results_per_query, strict=True):
        relevant = set(query.relevant_doc_ids)
        p = precision_at_k(results, relevant, k)
        r = recall_at_k(results, relevant, k)
        rr = reciprocal_rank(results, relevant)
        total_p += p
        total_r += r
        total_rr += rr
        per_query.append({"precision": p, "recall": r, "rr": rr})

    n = len(queries)
    return EvalMetrics(
        precision_at_k=total_p / n,
        recall_at_k=total_r / n,
        mrr=total_rr / n,
        num_queries=n,
        per_query=per_query,
    )
