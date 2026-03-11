"""LinkedIn platform adapter — enhanced simulation per ADR-006.

LinkedIn API requires Partner Program membership; this adapter simulates
interactions while logging intended actions for observability.
"""

from __future__ import annotations

import random
import time
from typing import Any

import structlog

from entwine.platforms.base import PlatformAdapter

log = structlog.get_logger(__name__)


def _synthetic_engagement() -> dict[str, int]:
    """Generate plausible LinkedIn engagement metrics."""
    return {
        "views": random.randint(50, 2000),
        "likes": random.randint(2, 80),
        "comments": random.randint(0, 15),
        "shares": random.randint(0, 8),
    }


class LinkedInSimAdapter(PlatformAdapter):
    """Simulated LinkedIn adapter that returns plausible synthetic responses.

    Records all intended actions in an internal log for observability.
    Designed to be swap-compatible with a real adapter if partner access
    is obtained.
    """

    def __init__(self) -> None:
        self._action_log: list[dict[str, Any]] = []

    @property
    def platform_name(self) -> str:
        return "linkedin"

    async def send(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        log.info("linkedin.send.simulated", action=action)
        entry = {
            "timestamp": time.time(),
            "action": action,
            "payload": payload,
            "status": "simulated",
        }
        self._action_log.append(entry)

        if action == "post_update":
            return {
                "status": "ok",
                "platform": "linkedin",
                "action": action,
                "simulated": True,
                "post_id": f"li_sim_{int(time.time() * 1000)}",
                "engagement": _synthetic_engagement(),
            }

        if action == "send_message":
            return {
                "status": "ok",
                "platform": "linkedin",
                "action": action,
                "simulated": True,
                "message_id": f"li_msg_{int(time.time() * 1000)}",
                "delivered": True,
            }

        return {
            "status": "ok",
            "platform": "linkedin",
            "action": action,
            "simulated": True,
            "payload": payload,
        }

    async def read(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        log.info("linkedin.read.simulated", query=query, limit=limit)
        posts = []
        for i in range(min(limit, 5)):
            posts.append(
                {
                    "id": f"li_post_{i}",
                    "text": f"Professional insight about {query} #{i + 1}",
                    "author": f"Professional {chr(65 + i)}",
                    "engagement": _synthetic_engagement(),
                }
            )
        return posts

    def available_actions(self) -> list[str]:
        return ["post_update", "read_feed", "send_message"]

    @property
    def action_log(self) -> list[dict[str, Any]]:
        """Return the recorded action log for observability."""
        return list(self._action_log)
