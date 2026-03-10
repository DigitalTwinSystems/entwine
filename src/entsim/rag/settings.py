"""RAG configuration via pydantic-settings."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class RAGSettings(BaseSettings):
    """Settings for the RAG pipeline (Qdrant + embeddings)."""

    model_config = SettingsConfigDict(
        env_prefix="RAG_",
        env_file=".env",
        extra="ignore",
    )

    qdrant_url: str = "http://localhost:6333"
    collection_name: str = "enterprise_knowledge"
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
