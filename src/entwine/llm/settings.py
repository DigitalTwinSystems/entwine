"""LLM settings loaded from environment variables."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMSettings(BaseSettings):
    """Configuration for LLM model names per tier.

    Environment variable names follow the pattern ``ENTWINE_LLM_<TIER>_MODEL``.
    """

    model_config = SettingsConfigDict(env_prefix="ENTWINE_LLM_", env_file=".env", extra="ignore")

    routine_model: str = "anthropic/claude-haiku-4-5"
    standard_model: str = "anthropic/claude-sonnet-4-6"
    complex_model: str = "anthropic/claude-opus-4-6"
