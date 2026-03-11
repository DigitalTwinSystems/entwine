"""Slack platform adapter using the official slack-sdk."""

from __future__ import annotations

from typing import Any

import structlog

from entwine.platforms.base import PlatformAdapter
from entwine.platforms.settings import SlackSettings

log = structlog.get_logger(__name__)


class SlackLiveAdapter(PlatformAdapter):
    """Real Slack adapter backed by ``slack_sdk.web.async_client``."""

    def __init__(self, settings: SlackSettings) -> None:
        from slack_sdk.web.async_client import AsyncWebClient

        self._settings = settings
        self._client = AsyncWebClient(token=settings.bot_token)
        self._default_channel = settings.default_channel

    @property
    def platform_name(self) -> str:
        return "slack"

    async def send(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        log.info("slack.send", action=action)
        if action == "send_message":
            channel = payload.get("channel", self._default_channel)
            text = payload.get("text", "")
            resp = await self._client.chat_postMessage(channel=channel, text=text)
            return {
                "status": "ok",
                "platform": "slack",
                "action": action,
                "simulated": False,
                "ts": resp.get("ts"),
                "channel": resp.get("channel"),
            }

        if action == "add_reaction":
            resp = await self._client.reactions_add(
                channel=payload["channel"],
                timestamp=payload["timestamp"],
                name=payload.get("emoji", "thumbsup"),
            )
            return {"status": "ok", "platform": "slack", "action": action, "simulated": False}

        return {"status": "error", "platform": "slack", "message": f"Unknown action: {action}"}

    async def read(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        log.info("slack.read", query=query, limit=limit)
        # Read recent messages from the default channel.
        resp = await self._client.conversations_history(channel=self._default_channel, limit=limit)
        messages: list[dict[str, Any]] = []
        for msg in resp.get("messages", []):
            messages.append(
                {
                    "id": msg.get("ts", ""),
                    "text": msg.get("text", ""),
                    "user": msg.get("user", ""),
                    "channel": self._default_channel,
                }
            )
        return messages

    def available_actions(self) -> list[str]:
        return ["send_message", "read_channel", "add_reaction"]
