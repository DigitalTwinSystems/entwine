"""Unit tests for platform adapters, registry, and factory."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from entwine.platforms.base import PlatformAdapter
from entwine.platforms.client import PlatformClient, RateLimiter, _parse_retry_after
from entwine.platforms.factory import build_platform_registry
from entwine.platforms.linkedin import LinkedInSimAdapter
from entwine.platforms.registry import PlatformRegistry
from entwine.platforms.settings import (
    GitHubSettings,
    PlatformSettings,
    SlackSettings,
)
from entwine.platforms.stubs import (
    EmailAdapter,
    GitHubAdapter,
    LinkedInAdapter,
    SlackAdapter,
    XAdapter,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ALL_STUB_ADAPTERS: list[type[PlatformAdapter]] = [
    XAdapter,
    LinkedInAdapter,
    GitHubAdapter,
    EmailAdapter,
    SlackAdapter,
]

EXPECTED_ACTIONS: dict[str, list[str]] = {
    "x": ["post_tweet", "read_timeline", "search_tweets"],
    "linkedin": ["post_update", "read_feed", "send_message"],
    "github": ["create_issue", "create_pr", "list_prs", "add_comment"],
    "email": ["send_email", "read_inbox"],
    "slack": ["send_message", "read_channel"],
}


def _make_registry() -> PlatformRegistry:
    reg = PlatformRegistry()
    for cls in ALL_STUB_ADAPTERS:
        reg.register(cls())
    return reg


# ---------------------------------------------------------------------------
# Stub adapter — send
# ---------------------------------------------------------------------------


class TestStubSend:
    @pytest.mark.parametrize("adapter_cls", ALL_STUB_ADAPTERS, ids=lambda c: c.__name__)
    async def test_send_returns_ok(self, adapter_cls: type[PlatformAdapter]) -> None:
        adapter = adapter_cls()
        result = await adapter.send("test_action", {"key": "value"})
        assert result["status"] == "ok"
        assert result["platform"] == adapter.platform_name
        assert result["action"] == "test_action"
        assert result["simulated"] is True


# ---------------------------------------------------------------------------
# Stub adapter — read
# ---------------------------------------------------------------------------


class TestStubRead:
    @pytest.mark.parametrize("adapter_cls", ALL_STUB_ADAPTERS, ids=lambda c: c.__name__)
    async def test_read_returns_items(self, adapter_cls: type[PlatformAdapter]) -> None:
        adapter = adapter_cls()
        items = await adapter.read("test_query")
        assert isinstance(items, list)
        assert len(items) >= 1

    async def test_read_respects_limit(self) -> None:
        adapter = XAdapter()
        items = await adapter.read("topic", limit=1)
        assert len(items) == 1


# ---------------------------------------------------------------------------
# Stub adapter — available_actions
# ---------------------------------------------------------------------------


class TestStubAvailableActions:
    @pytest.mark.parametrize("adapter_cls", ALL_STUB_ADAPTERS, ids=lambda c: c.__name__)
    def test_available_actions(self, adapter_cls: type[PlatformAdapter]) -> None:
        adapter = adapter_cls()
        actions = adapter.available_actions()
        assert actions == EXPECTED_ACTIONS[adapter.platform_name]


# ---------------------------------------------------------------------------
# PlatformRegistry — register / get / list
# ---------------------------------------------------------------------------


class TestPlatformRegistry:
    def test_register_and_get(self) -> None:
        reg = PlatformRegistry()
        adapter = XAdapter()
        reg.register(adapter)
        assert reg.get("x") is adapter

    def test_list_platforms(self) -> None:
        reg = _make_registry()
        platforms = reg.list_platforms()
        assert platforms == sorted(EXPECTED_ACTIONS)

    def test_list_all_actions(self) -> None:
        reg = _make_registry()
        actions = reg.list_all_actions()
        for name, expected in EXPECTED_ACTIONS.items():
            assert actions[name] == expected

    def test_unknown_platform_raises_keyerror(self) -> None:
        reg = PlatformRegistry()
        with pytest.raises(KeyError, match="no_such_platform"):
            reg.get("no_such_platform")

    def test_duplicate_register_raises_valueerror(self) -> None:
        reg = PlatformRegistry()
        reg.register(XAdapter())
        with pytest.raises(ValueError, match="already registered"):
            reg.register(XAdapter())


# ---------------------------------------------------------------------------
# LinkedInSimAdapter — enhanced simulation
# ---------------------------------------------------------------------------


class TestLinkedInSimAdapter:
    async def test_post_update_returns_engagement(self) -> None:
        adapter = LinkedInSimAdapter()
        result = await adapter.send("post_update", {"text": "Hello LinkedIn!"})
        assert result["status"] == "ok"
        assert result["simulated"] is True
        assert "engagement" in result
        assert "views" in result["engagement"]
        assert "likes" in result["engagement"]

    async def test_send_message(self) -> None:
        adapter = LinkedInSimAdapter()
        result = await adapter.send("send_message", {"to": "user", "text": "hi"})
        assert result["status"] == "ok"
        assert result["simulated"] is True
        assert result["delivered"] is True

    async def test_unknown_action_still_ok(self) -> None:
        adapter = LinkedInSimAdapter()
        result = await adapter.send("unknown_action", {"data": 1})
        assert result["status"] == "ok"
        assert result["simulated"] is True

    async def test_read_returns_posts_with_engagement(self) -> None:
        adapter = LinkedInSimAdapter()
        posts = await adapter.read("AI trends", limit=3)
        assert len(posts) == 3
        assert "engagement" in posts[0]

    def test_action_log_records_sends(self) -> None:
        import asyncio

        adapter = LinkedInSimAdapter()
        asyncio.get_event_loop().run_until_complete(adapter.send("post_update", {"text": "test"}))
        assert len(adapter.action_log) == 1
        assert adapter.action_log[0]["action"] == "post_update"

    def test_available_actions(self) -> None:
        adapter = LinkedInSimAdapter()
        assert adapter.available_actions() == ["post_update", "read_feed", "send_message"]


# ---------------------------------------------------------------------------
# RateLimiter
# ---------------------------------------------------------------------------


class TestRateLimiter:
    async def test_acquire_within_limit(self) -> None:
        rl = RateLimiter(max_calls=5, period_seconds=1.0)
        for _ in range(5):
            await rl.acquire()
        # Should not raise or block excessively.

    async def test_acquire_tracks_timestamps(self) -> None:
        rl = RateLimiter(max_calls=2, period_seconds=10.0)
        await rl.acquire()
        await rl.acquire()
        assert len(rl._timestamps) == 2


# ---------------------------------------------------------------------------
# _parse_retry_after
# ---------------------------------------------------------------------------


class TestParseRetryAfter:
    def test_retry_after_header(self) -> None:
        resp = MagicMock()
        resp.headers = {"retry-after": "3"}
        assert _parse_retry_after(resp) == 3.0

    def test_fallback_default(self) -> None:
        resp = MagicMock()
        resp.headers = {}
        assert _parse_retry_after(resp) == 5.0


# ---------------------------------------------------------------------------
# PlatformClient
# ---------------------------------------------------------------------------


class TestPlatformClient:
    async def test_close(self) -> None:
        client = PlatformClient(base_url="https://example.com")
        await client.close()  # Should not raise.


# ---------------------------------------------------------------------------
# Factory — build_platform_registry
# ---------------------------------------------------------------------------


class TestFactory:
    def test_no_credentials_returns_stubs(self) -> None:
        """With empty settings, all adapters should be stubs (except LinkedIn sim)."""
        settings = PlatformSettings()
        registry = build_platform_registry(settings)
        platforms = registry.list_platforms()
        assert sorted(platforms) == ["email", "github", "linkedin", "slack", "x"]

        # Verify stubs by checking simulated flag.
        import asyncio

        loop = asyncio.get_event_loop()
        for name in ["email", "github", "slack", "x"]:
            adapter = registry.get(name)
            result = loop.run_until_complete(adapter.send("test", {}))
            assert result["simulated"] is True

    def test_linkedin_always_simulated(self) -> None:
        registry = build_platform_registry(PlatformSettings())
        adapter = registry.get("linkedin")
        assert isinstance(adapter, LinkedInSimAdapter)

    def test_github_live_when_configured(self) -> None:
        settings = PlatformSettings()
        settings.github = GitHubSettings(token="ghp_test", owner="org", repo="repo")
        registry = build_platform_registry(settings)
        adapter = registry.get("github")
        # GitHubLiveAdapter doesn't need external deps; should be real.
        from entwine.platforms.github import GitHubLiveAdapter

        assert isinstance(adapter, GitHubLiveAdapter)

    def test_default_settings_when_none(self) -> None:
        """Passing None should use default PlatformSettings."""
        registry = build_platform_registry(None)
        assert len(registry.list_platforms()) == 5


# ---------------------------------------------------------------------------
# GitHub Live Adapter (unit, mocked HTTP)
# ---------------------------------------------------------------------------


class TestGitHubLiveAdapter:
    def _make_adapter(self) -> PlatformAdapter:
        from entwine.platforms.github import GitHubLiveAdapter

        return GitHubLiveAdapter(GitHubSettings(token="test", owner="org", repo="repo"))

    async def test_create_issue(self) -> None:
        adapter = self._make_adapter()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "number": 1,
            "html_url": "https://github.com/org/repo/issues/1",
        }
        mock_resp.status_code = 201
        mock_resp.raise_for_status = MagicMock()

        with patch.object(
            adapter._http, "_request", new_callable=AsyncMock, return_value=mock_resp
        ):
            result = await adapter.send("create_issue", {"title": "Bug", "body": "Fix it"})
        assert result["status"] == "ok"
        assert result["simulated"] is False
        assert result["issue_number"] == 1

    async def test_create_pr(self) -> None:
        adapter = self._make_adapter()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "number": 42,
            "html_url": "https://github.com/org/repo/pull/42",
        }
        mock_resp.raise_for_status = MagicMock()

        with patch.object(
            adapter._http, "_request", new_callable=AsyncMock, return_value=mock_resp
        ):
            result = await adapter.send("create_pr", {"title": "Fix", "head": "fix-branch"})
        assert result["status"] == "ok"
        assert result["pr_number"] == 42

    async def test_add_comment(self) -> None:
        adapter = self._make_adapter()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "id": 99,
            "html_url": "https://github.com/org/repo/issues/1#comment-99",
        }
        mock_resp.raise_for_status = MagicMock()

        with patch.object(
            adapter._http, "_request", new_callable=AsyncMock, return_value=mock_resp
        ):
            result = await adapter.send("add_comment", {"issue_number": 1, "body": "LGTM"})
        assert result["status"] == "ok"
        assert result["comment_id"] == 99

    async def test_list_prs(self) -> None:
        adapter = self._make_adapter()
        mock_resp = MagicMock()
        mock_resp.json.return_value = [
            {"number": 1, "title": "PR 1", "state": "open"},
            {"number": 2, "title": "PR 2", "state": "closed"},
        ]
        mock_resp.raise_for_status = MagicMock()

        with patch.object(
            adapter._http, "_request", new_callable=AsyncMock, return_value=mock_resp
        ):
            result = await adapter.send("list_prs", {})
        assert result["status"] == "ok"
        assert len(result["items"]) == 2

    async def test_read_search(self) -> None:
        adapter = self._make_adapter()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "items": [
                {"number": 10, "title": "Bug", "state": "open", "html_url": "https://..."},
            ]
        }
        mock_resp.raise_for_status = MagicMock()

        with patch.object(
            adapter._http, "_request", new_callable=AsyncMock, return_value=mock_resp
        ):
            items = await adapter.read("bug")
        assert len(items) == 1
        assert items[0]["title"] == "Bug"

    async def test_unknown_action(self) -> None:
        adapter = self._make_adapter()
        result = await adapter.send("nonexistent", {})
        assert result["status"] == "error"

    def test_available_actions(self) -> None:
        adapter = self._make_adapter()
        assert "create_issue" in adapter.available_actions()


# ---------------------------------------------------------------------------
# Slack Live Adapter (unit, mocked SDK)
# ---------------------------------------------------------------------------


class TestSlackLiveAdapter:
    def _make_adapter(self) -> PlatformAdapter:
        from entwine.platforms.slack import SlackLiveAdapter

        settings = SlackSettings(bot_token="xoxb-test", default_channel="#test")
        return SlackLiveAdapter(settings)

    async def test_send_message(self) -> None:
        adapter = self._make_adapter()
        adapter._client.chat_postMessage = AsyncMock(
            return_value={"ok": True, "ts": "123.456", "channel": "#test"}
        )
        result = await adapter.send("send_message", {"text": "Hello"})
        assert result["status"] == "ok"
        assert result["simulated"] is False
        assert result["ts"] == "123.456"

    async def test_add_reaction(self) -> None:
        adapter = self._make_adapter()
        adapter._client.reactions_add = AsyncMock(return_value={"ok": True})
        result = await adapter.send(
            "add_reaction", {"channel": "#test", "timestamp": "123.456", "emoji": "rocket"}
        )
        assert result["status"] == "ok"

    async def test_read_channel(self) -> None:
        adapter = self._make_adapter()
        adapter._client.conversations_history = AsyncMock(
            return_value={
                "ok": True,
                "messages": [
                    {"ts": "1", "text": "hello", "user": "U1"},
                    {"ts": "2", "text": "world", "user": "U2"},
                ],
            }
        )
        items = await adapter.read("query", limit=5)
        assert len(items) == 2
        assert items[0]["text"] == "hello"

    async def test_unknown_action(self) -> None:
        adapter = self._make_adapter()
        result = await adapter.send("nonexistent", {})
        assert result["status"] == "error"

    def test_available_actions(self) -> None:
        adapter = self._make_adapter()
        assert "send_message" in adapter.available_actions()
        assert "add_reaction" in adapter.available_actions()
