"""Platform credential settings loaded from environment variables."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class SlackSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ENTWINE_SLACK_", extra="ignore")

    bot_token: str = ""
    default_channel: str = "#general"


class GitHubSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ENTWINE_GITHUB_", extra="ignore")

    token: str = ""
    owner: str = ""
    repo: str = ""


class EmailSettings(BaseSettings):
    """Gmail via Google API."""

    model_config = SettingsConfigDict(env_prefix="ENTWINE_EMAIL_", extra="ignore")

    credentials_json: str = Field(default="", description="Path to Google OAuth credentials JSON.")
    token_json: str = Field(default="", description="Path to stored OAuth token JSON.")
    user_email: str = ""


class XSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ENTWINE_X_", extra="ignore")

    api_key: str = ""
    api_secret: str = ""
    access_token: str = ""
    access_token_secret: str = ""
    bearer_token: str = ""


class PlatformSettings(BaseSettings):
    """Aggregated platform credentials."""

    model_config = SettingsConfigDict(
        env_prefix="ENTWINE_",
        extra="ignore",
        env_nested_delimiter="__",
    )

    slack: SlackSettings = Field(default_factory=SlackSettings)
    github: GitHubSettings = Field(default_factory=GitHubSettings)
    email: EmailSettings = Field(default_factory=EmailSettings)
    x: XSettings = Field(default_factory=XSettings)
