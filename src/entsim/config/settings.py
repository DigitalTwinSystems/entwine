"""Application-level settings loaded from environment variables."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMSettings(BaseSettings):
    """Settings for the LiteLLM router / LLM providers."""

    model_config = SettingsConfigDict(env_prefix="ENTSIM_LLM_", extra="ignore")

    # Tier → model name mappings
    fast_model: str = Field(default="gpt-4o-mini", description="Model for 'fast' tier agents")
    standard_model: str = Field(default="gpt-4o", description="Model for 'standard' tier agents")
    premium_model: str = Field(default="gpt-4o", description="Model for 'premium' tier agents")

    # Provider keys (populated from env; never stored in config files)
    openai_api_key: str = Field(default="", description="OpenAI API key")
    anthropic_api_key: str = Field(default="", description="Anthropic API key")

    # Router settings
    max_retries: int = Field(default=3, ge=0)
    timeout_seconds: float = Field(default=60.0, gt=0)


class RAGSettings(BaseSettings):
    """Settings for the Qdrant-backed RAG layer."""

    model_config = SettingsConfigDict(env_prefix="ENTSIM_RAG_", extra="ignore")

    qdrant_url: str = Field(default="http://localhost:6333")
    qdrant_api_key: str = Field(default="")
    collection_prefix: str = Field(default="entsim")
    embedding_model: str = Field(default="text-embedding-3-small")
    top_k: int = Field(default=5, ge=1)


class AppSettings(BaseSettings):
    """Root application settings; layered file < env vars."""

    model_config = SettingsConfigDict(
        env_prefix="ENTSIM_",
        extra="ignore",
        # Allow nested models to read their own prefixed env vars
        env_nested_delimiter="__",
    )

    config_file: Path = Field(
        default=Path("entsim.yaml"),
        description="Path to the simulation config file (TOML or YAML).",
    )

    llm: LLMSettings = Field(default_factory=LLMSettings)
    rag: RAGSettings = Field(default_factory=RAGSettings)
