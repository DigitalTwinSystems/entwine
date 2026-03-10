"""Embedding service backed by the OpenAI embeddings API."""

from __future__ import annotations

import structlog
from openai import AsyncOpenAI

from entsim.rag.settings import RAGSettings

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


class EmbeddingService:
    """Generates dense vector embeddings using the OpenAI embeddings API."""

    def __init__(
        self,
        client: AsyncOpenAI | None = None,
        settings: RAGSettings | None = None,
    ) -> None:
        self._settings = settings or RAGSettings()
        self._client = client or AsyncOpenAI()

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return embeddings for *texts* using the configured OpenAI model.

        Args:
            texts: Non-empty list of strings to embed.

        Returns:
            A list of float vectors, one per input text, ordered identically.
        """
        if not texts:
            return []

        log = logger.bind(
            model=self._settings.embedding_model,
            dimensions=self._settings.embedding_dimensions,
            num_texts=len(texts),
        )
        log.debug("embedding.request")

        response = await self._client.embeddings.create(
            input=texts,
            model=self._settings.embedding_model,
            dimensions=self._settings.embedding_dimensions,
        )

        embeddings = [item.embedding for item in response.data]
        log.debug("embedding.response", num_embeddings=len(embeddings))
        return embeddings
