"""Knowledge store: Qdrant-backed document storage and hybrid search."""

from __future__ import annotations

import math
import re
from collections import Counter

import structlog
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchAny,
    PointStruct,
    SparseVector,
    SparseVectorParams,
    VectorParams,
)

from entwine.rag.embeddings import EmbeddingService
from entwine.rag.models import Document, SearchResult
from entwine.rag.settings import RAGSettings

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

_SPARSE_VECTOR_NAME = "text_sparse"
_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


class KnowledgeStore:
    """Qdrant-backed vector store for enterprise documents.

    Supports upserting documents and role-filtered semantic search.
    When ``enable_hybrid`` is set, combines dense and sparse (BM25-style)
    retrieval using Reciprocal Rank Fusion (RRF).
    """

    def __init__(
        self,
        client: AsyncQdrantClient | None = None,
        embedding_service: EmbeddingService | None = None,
        settings: RAGSettings | None = None,
    ) -> None:
        self._settings = settings or RAGSettings()
        self._client = client or AsyncQdrantClient(url=self._settings.qdrant_url)
        self._embeddings = embedding_service or EmbeddingService(settings=self._settings)

    async def init_collection(self) -> None:
        """Create the Qdrant collection if it does not already exist."""
        log = logger.bind(collection=self._settings.collection_name)
        exists = await self._client.collection_exists(self._settings.collection_name)
        if exists:
            log.info("store.collection_already_exists")
            return

        sparse_vectors_config = None
        if self._settings.enable_hybrid:
            sparse_vectors_config = {
                _SPARSE_VECTOR_NAME: SparseVectorParams(),
            }

        await self._client.create_collection(
            collection_name=self._settings.collection_name,
            vectors_config=VectorParams(
                size=self._settings.embedding_dimensions,
                distance=Distance.COSINE,
            ),
            sparse_vectors_config=sparse_vectors_config,
        )
        log.info(
            "store.collection_created",
            dimensions=self._settings.embedding_dimensions,
            hybrid=self._settings.enable_hybrid,
        )

    async def get_existing_ids(self, ids: list[str]) -> set[str]:
        """Return the subset of *ids* that already exist in the collection."""
        if not ids:
            return set()
        try:
            points = await self._client.retrieve(
                collection_name=self._settings.collection_name,
                ids=ids,
                with_payload=False,
                with_vectors=False,
            )
            return {str(p.id) for p in points}
        except Exception:
            logger.warning("store.get_existing_ids_failed", exc_info=True)
            return set()

    async def upsert(self, documents: list[Document]) -> None:
        """Embed *documents* and upsert them into the collection.

        Args:
            documents: List of documents to store. Existing documents with the
                same id will be overwritten.
        """
        if not documents:
            return

        log = logger.bind(
            collection=self._settings.collection_name,
            num_documents=len(documents),
        )
        log.debug("store.upsert_start")

        texts = [doc.content for doc in documents]
        vectors = await self._embeddings.embed(texts)

        points = []
        for doc, vector in zip(documents, vectors, strict=True):
            point_vector: dict | list[float] = vector
            if self._settings.enable_hybrid:
                sparse = self._build_sparse_vector(doc.content)
                point_vector = {
                    "": vector,
                    _SPARSE_VECTOR_NAME: sparse,
                }
            points.append(
                PointStruct(
                    id=doc.id,
                    vector=point_vector,
                    payload={"content": doc.content, **doc.metadata},
                )
            )

        await self._client.upsert(
            collection_name=self._settings.collection_name,
            points=points,
        )
        log.info("store.upsert_complete")

    async def search(
        self,
        query: str,
        agent_roles: list[str] | str | None = None,
        *,
        agent_role: str | None = None,
        limit: int = 5,
    ) -> list[SearchResult]:
        """Search the collection for documents accessible by the agent's roles.

        Args:
            query: Natural-language query string.
            agent_roles: List of roles the agent has access to. Documents whose
                ``accessible_roles`` metadata list contains any of these values
                (or ``"company-wide"``) are returned.
            agent_role: Deprecated single-role string. Kept for backward compat.
            limit: Maximum number of results to return.

        Returns:
            Ranked list of :class:`SearchResult` objects (highest score first).
        """
        # Normalize roles: accept list, single string, or legacy kwarg
        roles: list[str]
        if agent_roles is not None:
            roles = [agent_roles] if isinstance(agent_roles, str) else list(agent_roles)
        elif agent_role is not None:
            roles = [agent_role]
        else:
            roles = []

        # Always include "company-wide" so company-wide docs are accessible to all
        all_match_roles = list({*roles, "company-wide"})

        log = logger.bind(
            collection=self._settings.collection_name,
            agent_roles=all_match_roles,
            limit=limit,
        )
        log.debug("store.search_start")

        query_vectors = await self._embeddings.embed([query])
        query_vector = query_vectors[0]

        role_filter = Filter(
            must=[
                FieldCondition(
                    key="accessible_roles",
                    match=MatchAny(any=all_match_roles),
                )
            ]
        )

        # Dense search (always performed)
        hits = await self._client.search(
            collection_name=self._settings.collection_name,
            query_vector=query_vector,
            query_filter=role_filter,
            limit=limit,
            with_payload=True,
        )

        dense_results = self._hits_to_results(hits)

        if not self._settings.enable_hybrid:
            log.info("store.search_complete", num_results=len(dense_results))
            return dense_results

        # Sparse search
        sparse_query = self._build_sparse_vector(query)
        sparse_response = await self._client.query_points(
            collection_name=self._settings.collection_name,
            query=sparse_query,
            using=_SPARSE_VECTOR_NAME,
            query_filter=role_filter,
            limit=limit,
            with_payload=True,
        )
        sparse_results = self._hits_to_results(sparse_response.points)

        fused = self._rrf_fuse(dense_results, sparse_results, limit=limit, k=self._settings.rrf_k)
        log.info("store.search_complete", num_results=len(fused), hybrid=True)
        return fused

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_sparse_vector(text: str) -> SparseVector:
        """Create a BM25-style sparse vector from *text*.

        Tokenises by extracting lowercase alphanumeric tokens, counts term
        frequencies, applies a simple ``1 + log(tf)`` weighting, and hashes
        each token to produce a sparse index.
        """
        tokens = _TOKEN_PATTERN.findall(text.lower())
        if not tokens:
            return SparseVector(indices=[], values=[])

        counts = Counter(tokens)
        indices: list[int] = []
        values: list[float] = []
        for term, count in sorted(counts.items()):
            idx = hash(term) & 0xFFFFFFFF  # unsigned 32-bit
            weight = 1.0 + math.log(count)
            indices.append(idx)
            values.append(weight)

        return SparseVector(indices=indices, values=values)

    @staticmethod
    def _hits_to_results(hits: list) -> list[SearchResult]:
        """Convert a list of Qdrant scored points to SearchResult objects."""
        results: list[SearchResult] = []
        for hit in hits:
            payload = dict(hit.payload) if hit.payload else {}
            content = str(payload.pop("content", ""))
            doc = Document(id=str(hit.id), content=content, metadata=payload)
            results.append(SearchResult(document=doc, score=hit.score))
        return results

    @staticmethod
    def _rrf_fuse(
        dense_results: list[SearchResult],
        sparse_results: list[SearchResult],
        *,
        limit: int = 5,
        k: int = 60,
    ) -> list[SearchResult]:
        """Fuse two ranked lists using Reciprocal Rank Fusion (RRF).

        For each document, the fused score is:
            ``score = sum(1 / (k + rank_i))``
        where *k* defaults to 60 (the standard RRF constant) and *rank_i* is the
        1-based rank in each result list the document appears in.
        """
        doc_map: dict[str, SearchResult] = {}
        scores: dict[str, float] = {}

        for rank, result in enumerate(dense_results, start=1):
            doc_id = result.document.id
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
            if doc_id not in doc_map:
                doc_map[doc_id] = result

        for rank, result in enumerate(sparse_results, start=1):
            doc_id = result.document.id
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
            if doc_id not in doc_map:
                doc_map[doc_id] = result

        ranked_ids = sorted(scores, key=lambda did: scores[did], reverse=True)[:limit]
        return [
            SearchResult(document=doc_map[did].document, score=scores[did]) for did in ranked_ids
        ]
