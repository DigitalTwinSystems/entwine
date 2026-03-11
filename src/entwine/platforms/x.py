"""X (Twitter) platform adapter using tweepy."""

from __future__ import annotations

from typing import Any

import structlog

from entwine.platforms.base import PlatformAdapter
from entwine.platforms.settings import XSettings

log = structlog.get_logger(__name__)


class XLiveAdapter(PlatformAdapter):
    """Real X/Twitter adapter backed by ``tweepy.asynchronous.AsyncClient``."""

    def __init__(self, settings: XSettings) -> None:
        import tweepy

        self._settings = settings
        self._client = tweepy.asynchronous.AsyncClient(
            consumer_key=settings.api_key,
            consumer_secret=settings.api_secret,
            access_token=settings.access_token,
            access_token_secret=settings.access_token_secret,
            bearer_token=settings.bearer_token,
        )

    @property
    def platform_name(self) -> str:
        return "x"

    async def send(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        log.info("x.send", action=action)
        if action == "post_tweet":
            text = payload.get("text", "")
            reply_to = payload.get("reply_to")
            resp = await self._client.create_tweet(
                text=text,
                in_reply_to_tweet_id=reply_to,
            )
            tweet_data = resp.data or {}
            return {
                "status": "ok",
                "platform": "x",
                "action": action,
                "simulated": False,
                "tweet_id": tweet_data.get("id"),
            }

        return {"status": "error", "platform": "x", "message": f"Unknown action: {action}"}

    async def read(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        log.info("x.read", query=query, limit=limit)
        resp = await self._client.search_recent_tweets(query=query, max_results=max(limit, 10))
        items: list[dict[str, Any]] = []
        for tweet in resp.data or []:
            items.append(
                {
                    "id": tweet.id,
                    "text": tweet.text,
                    "author_id": tweet.author_id,
                }
            )
        return items[:limit]

    def available_actions(self) -> list[str]:
        return ["post_tweet", "read_timeline", "search_tweets"]
