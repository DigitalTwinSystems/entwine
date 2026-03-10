"""Stub platform adapters that return synthetic data for simulation."""

from __future__ import annotations

import structlog

from entsim.platforms.base import PlatformAdapter

log = structlog.get_logger(__name__)


def _ok(platform: str, action: str, **extras: object) -> dict:
    """Build a standard success-response dict."""
    return {"status": "ok", "platform": platform, "action": action, "simulated": True, **extras}


# ---------------------------------------------------------------------------
# X (formerly Twitter)
# ---------------------------------------------------------------------------


class XAdapter(PlatformAdapter):
    """Stub adapter for the X platform."""

    @property
    def platform_name(self) -> str:
        return "x"

    async def send(self, action: str, payload: dict) -> dict:
        log.info("platform.send", platform=self.platform_name, action=action)
        return _ok(self.platform_name, action, payload=payload)

    async def read(self, query: str, limit: int = 10) -> list[dict]:
        log.info("platform.read", platform=self.platform_name, query=query)
        return [
            {"id": "tweet_1", "text": f"Synthetic tweet about {query}", "author": "sim_user_1"},
            {"id": "tweet_2", "text": f"Another tweet mentioning {query}", "author": "sim_user_2"},
        ][:limit]

    def available_actions(self) -> list[str]:
        return ["post_tweet", "read_timeline", "search_tweets"]


# ---------------------------------------------------------------------------
# LinkedIn
# ---------------------------------------------------------------------------


class LinkedInAdapter(PlatformAdapter):
    """Stub adapter for the LinkedIn platform."""

    @property
    def platform_name(self) -> str:
        return "linkedin"

    async def send(self, action: str, payload: dict) -> dict:
        log.info("platform.send", platform=self.platform_name, action=action)
        return _ok(self.platform_name, action, payload=payload)

    async def read(self, query: str, limit: int = 10) -> list[dict]:
        log.info("platform.read", platform=self.platform_name, query=query)
        return [
            {"id": "li_post_1", "text": f"LinkedIn post about {query}", "author": "Professional A"},
            {"id": "li_post_2", "text": f"LinkedIn update on {query}", "author": "Professional B"},
        ][:limit]

    def available_actions(self) -> list[str]:
        return ["post_update", "read_feed", "send_message"]


# ---------------------------------------------------------------------------
# GitHub
# ---------------------------------------------------------------------------


class GitHubAdapter(PlatformAdapter):
    """Stub adapter for the GitHub platform."""

    @property
    def platform_name(self) -> str:
        return "github"

    async def send(self, action: str, payload: dict) -> dict:
        log.info("platform.send", platform=self.platform_name, action=action)
        return _ok(self.platform_name, action, payload=payload)

    async def read(self, query: str, limit: int = 10) -> list[dict]:
        log.info("platform.read", platform=self.platform_name, query=query)
        return [
            {"id": "issue_101", "title": f"Issue about {query}", "state": "open"},
            {"id": "pr_42", "title": f"PR related to {query}", "state": "open"},
        ][:limit]

    def available_actions(self) -> list[str]:
        return ["create_issue", "create_pr", "list_prs", "add_comment"]


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------


class EmailAdapter(PlatformAdapter):
    """Stub adapter for email."""

    @property
    def platform_name(self) -> str:
        return "email"

    async def send(self, action: str, payload: dict) -> dict:
        log.info("platform.send", platform=self.platform_name, action=action)
        return _ok(self.platform_name, action, payload=payload)

    async def read(self, query: str, limit: int = 10) -> list[dict]:
        log.info("platform.read", platform=self.platform_name, query=query)
        return [
            {"id": "msg_1", "subject": f"Re: {query}", "from": "alice@example.com"},
            {"id": "msg_2", "subject": f"Fwd: {query}", "from": "bob@example.com"},
        ][:limit]

    def available_actions(self) -> list[str]:
        return ["send_email", "read_inbox"]


# ---------------------------------------------------------------------------
# Slack
# ---------------------------------------------------------------------------


class SlackAdapter(PlatformAdapter):
    """Stub adapter for Slack."""

    @property
    def platform_name(self) -> str:
        return "slack"

    async def send(self, action: str, payload: dict) -> dict:
        log.info("platform.send", platform=self.platform_name, action=action)
        return _ok(self.platform_name, action, payload=payload)

    async def read(self, query: str, limit: int = 10) -> list[dict]:
        log.info("platform.read", platform=self.platform_name, query=query)
        return [
            {"id": "slack_1", "text": f"Message about {query}", "channel": "#general"},
            {"id": "slack_2", "text": f"Reply regarding {query}", "channel": "#general"},
        ][:limit]

    def available_actions(self) -> list[str]:
        return ["send_message", "read_channel"]
