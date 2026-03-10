"""Application-level settings loaded from environment variables."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from entwine.llm.settings import LLMSettings
from entwine.rag.settings import RAGSettings


class AppSettings(BaseSettings):
    """Root application settings; layered file < env vars."""

    model_config = SettingsConfigDict(
        env_prefix="ENTWINE_",
        extra="ignore",
        env_nested_delimiter="__",
    )

    config_file: Path = Field(
        default=Path("entwine.yaml"),
        description="Path to the simulation config file (TOML or YAML).",
    )

    llm: LLMSettings = Field(default_factory=LLMSettings)
    rag: RAGSettings = Field(default_factory=RAGSettings)
