"""Unit tests for platform adapter stubs and the platform registry."""

from __future__ import annotations

import pytest

from entwine.platforms.base import PlatformAdapter
from entwine.platforms.registry import PlatformRegistry
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

ALL_ADAPTERS: list[type[PlatformAdapter]] = [
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
    for cls in ALL_ADAPTERS:
        reg.register(cls())
    return reg


# ---------------------------------------------------------------------------
# Stub adapter — send
# ---------------------------------------------------------------------------


class TestStubSend:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("adapter_cls", ALL_ADAPTERS, ids=lambda c: c.__name__)
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
    @pytest.mark.asyncio
    @pytest.mark.parametrize("adapter_cls", ALL_ADAPTERS, ids=lambda c: c.__name__)
    async def test_read_returns_items(self, adapter_cls: type[PlatformAdapter]) -> None:
        adapter = adapter_cls()
        items = await adapter.read("test_query")
        assert isinstance(items, list)
        assert len(items) >= 1

    @pytest.mark.asyncio
    async def test_read_respects_limit(self) -> None:
        adapter = XAdapter()
        items = await adapter.read("topic", limit=1)
        assert len(items) == 1


# ---------------------------------------------------------------------------
# Stub adapter — available_actions
# ---------------------------------------------------------------------------


class TestStubAvailableActions:
    @pytest.mark.parametrize("adapter_cls", ALL_ADAPTERS, ids=lambda c: c.__name__)
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
