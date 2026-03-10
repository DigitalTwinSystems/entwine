"""Knowledge store: Qdrant-backed document storage and hybrid search."""

from __future__ import annotations

import structlog
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchAny,
    PointStruct,
    VectorParams,
)

from entsim.rag.embeddings import EmbeddingService
from entsim.rag.models import Document, SearchResult
from entsim.rag.settings import RAGSettings

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


class KnowledgeStore:
    """Qdrant-backed vector store for enterprise documents.

    Supports upserting documents and role-filtered semantic search.
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

        await self._client.create_collection(
            collection_name=self._settings.collection_name,
            vectors_config=VectorParams(
                size=self._settings.embedding_dimensions,
                distance=Distance.COSINE,
            ),
        )
        log.info("store.collection_created", dimensions=self._settings.embedding_dimensions)

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

        points = [
            PointStruct(
                id=doc.id,
                vector=vector,
                payload={"content": doc.content, **doc.metadata},
            )
            for doc, vector in zip(documents, vectors, strict=True)
        ]

        await self._client.upsert(
            collection_name=self._settings.collection_name,
            points=points,
        )
        log.info("store.upsert_complete")

    async def search(
        self,
        query: str,
        agent_role: str,
        limit: int = 5,
    ) -> list[SearchResult]:
        """Search the collection for documents accessible by *agent_role*.

        Args:
            query: Natural-language query string.
            agent_role: The role of the requesting agent; only documents whose
                ``accessible_roles`` metadata list contains this value are returned.
            limit: Maximum number of results to return.

        Returns:
            Ranked list of :class:`SearchResult` objects (highest score first).
        """
        log = logger.bind(
            collection=self._settings.collection_name,
            agent_role=agent_role,
            limit=limit,
        )
        log.debug("store.search_start")

        query_vectors = await self._embeddings.embed([query])
        query_vector = query_vectors[0]

        role_filter = Filter(
            must=[
                FieldCondition(
                    key="accessible_roles",
                    match=MatchAny(any=[agent_role]),
                )
            ]
        )

        hits = await self._client.search(
            collection_name=self._settings.collection_name,
            query_vector=query_vector,
            query_filter=role_filter,
            limit=limit,
            with_payload=True,
        )

        results: list[SearchResult] = []
        for hit in hits:
            payload = dict(hit.payload) if hit.payload else {}
            content = str(payload.pop("content", ""))
            doc = Document(id=str(hit.id), content=content, metadata=payload)
            results.append(SearchResult(document=doc, score=hit.score))

        log.info("store.search_complete", num_results=len(results))
        return results
