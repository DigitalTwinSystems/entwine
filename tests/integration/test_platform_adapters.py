"""Integration tests for platform adapters — require real credentials.

Run with: uv run pytest tests/integration/test_platform_adapters.py -m integration
Set environment variables per .env.example before running.
"""

from __future__ import annotations

import os

import pytest

from entwine.platforms.factory import build_platform_registry
from entwine.platforms.settings import PlatformSettings

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _settings() -> PlatformSettings:
    return PlatformSettings()


def _has_env(*keys: str) -> bool:
    return all(os.environ.get(k) for k in keys)


# ---------------------------------------------------------------------------
# Slack
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not _has_env("ENTWINE_SLACK_BOT_TOKEN"),
    reason="ENTWINE_SLACK_BOT_TOKEN not set",
)
class TestSlackIntegration:
    async def test_read_channel(self) -> None:
        registry = build_platform_registry(_settings())
        adapter = registry.get("slack")
        items = await adapter.read("recent", limit=3)
        assert isinstance(items, list)

    async def test_send_message(self) -> None:
        registry = build_platform_registry(_settings())
        adapter = registry.get("slack")
        result = await adapter.send("send_message", {"text": "[entwine integration test]"})
        assert result["status"] == "ok"
        assert result["simulated"] is False


# ---------------------------------------------------------------------------
# GitHub
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not _has_env("ENTWINE_GITHUB_TOKEN", "ENTWINE_GITHUB_OWNER", "ENTWINE_GITHUB_REPO"),
    reason="GitHub credentials not set",
)
class TestGitHubIntegration:
    async def test_read_issues(self) -> None:
        registry = build_platform_registry(_settings())
        adapter = registry.get("github")
        items = await adapter.read("is:issue", limit=5)
        assert isinstance(items, list)

    async def test_list_prs(self) -> None:
        registry = build_platform_registry(_settings())
        adapter = registry.get("github")
        result = await adapter.send("list_prs", {"state": "open", "limit": 3})
        assert result["status"] == "ok"


# ---------------------------------------------------------------------------
# X (Twitter)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not _has_env("ENTWINE_X_BEARER_TOKEN"),
    reason="ENTWINE_X_BEARER_TOKEN not set",
)
class TestXIntegration:
    async def test_search_tweets(self) -> None:
        registry = build_platform_registry(_settings())
        adapter = registry.get("x")
        items = await adapter.read("python", limit=5)
        assert isinstance(items, list)


# ---------------------------------------------------------------------------
# Email (Gmail)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not _has_env("ENTWINE_EMAIL_CREDENTIALS_JSON", "ENTWINE_EMAIL_TOKEN_JSON"),
    reason="Gmail credentials not set",
)
class TestEmailIntegration:
    async def test_read_inbox(self) -> None:
        registry = build_platform_registry(_settings())
        adapter = registry.get("email")
        items = await adapter.read("in:inbox", limit=3)
        assert isinstance(items, list)


# ---------------------------------------------------------------------------
# LinkedIn (always simulated)
# ---------------------------------------------------------------------------


class TestLinkedInIntegration:
    async def test_always_simulated(self) -> None:
        registry = build_platform_registry(_settings())
        adapter = registry.get("linkedin")
        result = await adapter.send("post_update", {"text": "test"})
        assert result["simulated"] is True
