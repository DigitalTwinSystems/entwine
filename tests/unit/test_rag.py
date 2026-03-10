"""Unit tests for the RAG pipeline (models, embeddings, store)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from entsim.rag.embeddings import EmbeddingService
from entsim.rag.models import Document, SearchResult
from entsim.rag.settings import RAGSettings
from entsim.rag.store import KnowledgeStore

# ---------------------------------------------------------------------------
# Document model
# ---------------------------------------------------------------------------


class TestDocumentModel:
    def test_minimal_document(self) -> None:
        doc = Document(id="doc-1", content="Hello world")
        assert doc.id == "doc-1"
        assert doc.content == "Hello world"
        assert doc.metadata == {}

    def test_document_with_full_metadata(self) -> None:
        doc = Document(
            id="doc-2",
            content="Quarterly roadmap",
            metadata={
                "department": "engineering",
                "sensitivity": "internal",
                "accessible_roles": ["cto", "developer"],
                "source": "confluence",
                "updated_at": "2026-03-10T12:00:00Z",
            },
        )
        assert doc.metadata["department"] == "engineering"
        assert "developer" in doc.metadata["accessible_roles"]

    def test_document_missing_required_fields(self) -> None:
        with pytest.raises(ValidationError):
            Document(content="No id")  # type: ignore[call-arg]

    def test_document_id_must_be_string(self) -> None:
        # Pydantic coerces int → str in lax mode; ensure object is still valid.
        doc = Document(id="42", content="some text")
        assert doc.id == "42"


class TestSearchResultModel:
    def test_search_result(self) -> None:
        doc = Document(id="doc-1", content="text")
        result = SearchResult(document=doc, score=0.95)
        assert result.score == pytest.approx(0.95)
        assert result.document.id == "doc-1"

    def test_search_result_missing_score(self) -> None:
        doc = Document(id="doc-1", content="text")
        with pytest.raises(ValidationError):
            SearchResult(document=doc)  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# EmbeddingService
# ---------------------------------------------------------------------------


def _make_embedding_response(vectors: list[list[float]]) -> MagicMock:
    """Build a mock object that mimics openai.types.CreateEmbeddingResponse."""
    response = MagicMock()
    response.data = [MagicMock(embedding=v) for v in vectors]
    return response


@pytest.fixture()
def rag_settings() -> RAGSettings:
    return RAGSettings(
        qdrant_url="http://localhost:6333",
        collection_name="test_collection",
        embedding_model="text-embedding-3-small",
        embedding_dimensions=1536,
    )


@pytest.fixture()
def mock_openai_client() -> MagicMock:
    client = MagicMock()
    client.embeddings = MagicMock()
    client.embeddings.create = AsyncMock()
    return client


class TestEmbeddingService:
    @pytest.mark.asyncio
    async def test_embed_single_text(
        self,
        mock_openai_client: MagicMock,
        rag_settings: RAGSettings,
    ) -> None:
        vector = [0.1] * 1536
        mock_openai_client.embeddings.create.return_value = _make_embedding_response([vector])

        service = EmbeddingService(client=mock_openai_client, settings=rag_settings)
        result = await service.embed(["hello"])

        assert len(result) == 1
        assert result[0] == vector
        mock_openai_client.embeddings.create.assert_awaited_once_with(
            input=["hello"],
            model="text-embedding-3-small",
            dimensions=1536,
        )

    @pytest.mark.asyncio
    async def test_embed_multiple_texts(
        self,
        mock_openai_client: MagicMock,
        rag_settings: RAGSettings,
    ) -> None:
        vectors = [[float(i)] * 4 for i in range(3)]
        mock_openai_client.embeddings.create.return_value = _make_embedding_response(vectors)

        service = EmbeddingService(client=mock_openai_client, settings=rag_settings)
        result = await service.embed(["a", "b", "c"])

        assert len(result) == 3
        assert result[1] == vectors[1]

    @pytest.mark.asyncio
    async def test_embed_empty_list(
        self,
        mock_openai_client: MagicMock,
        rag_settings: RAGSettings,
    ) -> None:
        service = EmbeddingService(client=mock_openai_client, settings=rag_settings)
        result = await service.embed([])

        assert result == []
        mock_openai_client.embeddings.create.assert_not_awaited()


# ---------------------------------------------------------------------------
# KnowledgeStore
# ---------------------------------------------------------------------------


def _make_qdrant_hit(
    doc_id: str,
    content: str,
    score: float,
    metadata: dict[str, Any] | None = None,
) -> MagicMock:
    hit = MagicMock()
    hit.id = doc_id
    hit.score = score
    payload: dict[str, Any] = {"content": content}
    if metadata:
        payload.update(metadata)
    hit.payload = payload
    return hit


@pytest.fixture()
def mock_qdrant_client() -> MagicMock:
    client = MagicMock()
    client.collection_exists = AsyncMock(return_value=False)
    client.create_collection = AsyncMock()
    client.upsert = AsyncMock()
    client.search = AsyncMock(return_value=[])
    return client


@pytest.fixture()
def mock_embedding_service() -> MagicMock:
    service = MagicMock(spec=EmbeddingService)
    service.embed = AsyncMock(return_value=[[0.1] * 1536])
    return service


class TestKnowledgeStoreSearch:
    @pytest.mark.asyncio
    async def test_search_returns_role_filtered_results(
        self,
        mock_qdrant_client: MagicMock,
        mock_embedding_service: MagicMock,
        rag_settings: RAGSettings,
    ) -> None:
        hits = [
            _make_qdrant_hit(
                "doc-1",
                "Engineering roadmap Q2",
                0.92,
                {
                    "department": "engineering",
                    "sensitivity": "internal",
                    "accessible_roles": ["cto", "developer"],
                    "source": "confluence",
                    "updated_at": "2026-03-10T12:00:00Z",
                },
            ),
        ]
        mock_qdrant_client.search.return_value = hits

        store = KnowledgeStore(
            client=mock_qdrant_client,
            embedding_service=mock_embedding_service,
            settings=rag_settings,
        )
        results = await store.search("roadmap", agent_role="developer", limit=5)

        assert len(results) == 1
        assert results[0].document.id == "doc-1"
        assert results[0].score == pytest.approx(0.92)
        assert results[0].document.content == "Engineering roadmap Q2"
        assert results[0].document.metadata["department"] == "engineering"

    @pytest.mark.asyncio
    async def test_search_passes_role_filter_to_qdrant(
        self,
        mock_qdrant_client: MagicMock,
        mock_embedding_service: MagicMock,
        rag_settings: RAGSettings,
    ) -> None:
        mock_qdrant_client.search.return_value = []

        store = KnowledgeStore(
            client=mock_qdrant_client,
            embedding_service=mock_embedding_service,
            settings=rag_settings,
        )
        await store.search("anything", agent_role="cto", limit=3)

        call_kwargs = mock_qdrant_client.search.call_args.kwargs
        assert call_kwargs["collection_name"] == "test_collection"
        assert call_kwargs["limit"] == 3
        # Filter must be present
        assert call_kwargs["query_filter"] is not None

    @pytest.mark.asyncio
    async def test_search_empty_results(
        self,
        mock_qdrant_client: MagicMock,
        mock_embedding_service: MagicMock,
        rag_settings: RAGSettings,
    ) -> None:
        mock_qdrant_client.search.return_value = []

        store = KnowledgeStore(
            client=mock_qdrant_client,
            embedding_service=mock_embedding_service,
            settings=rag_settings,
        )
        results = await store.search("nothing matches", agent_role="intern", limit=5)

        assert results == []

    @pytest.mark.asyncio
    async def test_init_collection_creates_when_missing(
        self,
        mock_qdrant_client: MagicMock,
        mock_embedding_service: MagicMock,
        rag_settings: RAGSettings,
    ) -> None:
        mock_qdrant_client.collection_exists.return_value = False

        store = KnowledgeStore(
            client=mock_qdrant_client,
            embedding_service=mock_embedding_service,
            settings=rag_settings,
        )
        await store.init_collection()

        mock_qdrant_client.create_collection.assert_awaited_once()
        call_kwargs = mock_qdrant_client.create_collection.call_args.kwargs
        assert call_kwargs["collection_name"] == "test_collection"

    @pytest.mark.asyncio
    async def test_init_collection_skips_when_exists(
        self,
        mock_qdrant_client: MagicMock,
        mock_embedding_service: MagicMock,
        rag_settings: RAGSettings,
    ) -> None:
        mock_qdrant_client.collection_exists.return_value = True

        store = KnowledgeStore(
            client=mock_qdrant_client,
            embedding_service=mock_embedding_service,
            settings=rag_settings,
        )
        await store.init_collection()

        mock_qdrant_client.create_collection.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_upsert_embeds_and_stores(
        self,
        mock_qdrant_client: MagicMock,
        rag_settings: RAGSettings,
    ) -> None:
        vectors = [[float(i)] * 1536 for i in range(2)]
        embedding_service = MagicMock(spec=EmbeddingService)
        embedding_service.embed = AsyncMock(return_value=vectors)

        docs = [
            Document(id="d1", content="First doc"),
            Document(id="d2", content="Second doc"),
        ]

        store = KnowledgeStore(
            client=mock_qdrant_client,
            embedding_service=embedding_service,
            settings=rag_settings,
        )
        await store.upsert(docs)

        embedding_service.embed.assert_awaited_once_with(["First doc", "Second doc"])
        mock_qdrant_client.upsert.assert_awaited_once()
        upsert_kwargs = mock_qdrant_client.upsert.call_args.kwargs
        assert upsert_kwargs["collection_name"] == "test_collection"
        assert len(upsert_kwargs["points"]) == 2

    @pytest.mark.asyncio
    async def test_upsert_empty_list_is_noop(
        self,
        mock_qdrant_client: MagicMock,
        mock_embedding_service: MagicMock,
        rag_settings: RAGSettings,
    ) -> None:
        store = KnowledgeStore(
            client=mock_qdrant_client,
            embedding_service=mock_embedding_service,
            settings=rag_settings,
        )
        await store.upsert([])

        mock_qdrant_client.upsert.assert_not_awaited()
        mock_embedding_service.embed.assert_not_awaited()
