"""GitHub platform adapter using httpx against the REST API."""

from __future__ import annotations

from typing import Any

import structlog

from entwine.platforms.base import PlatformAdapter
from entwine.platforms.client import PlatformClient, RateLimiter
from entwine.platforms.settings import GitHubSettings

log = structlog.get_logger(__name__)

# GitHub REST: 5000 req/hr authenticated ≈ 83/min.
_GH_RATE = RateLimiter(max_calls=80, period_seconds=60)


class GitHubLiveAdapter(PlatformAdapter):
    """Real GitHub adapter using REST API via httpx."""

    def __init__(self, settings: GitHubSettings) -> None:
        self._settings = settings
        self._owner = settings.owner
        self._repo = settings.repo
        self._http = PlatformClient(
            base_url="https://api.github.com",
            rate_limiter=_GH_RATE,
            headers={
                "Authorization": f"Bearer {settings.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )

    @property
    def platform_name(self) -> str:
        return "github"

    async def send(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        log.info("github.send", action=action)
        owner = payload.get("owner", self._owner)
        repo = payload.get("repo", self._repo)

        if action == "create_issue":
            resp = await self._http._request(
                "POST",
                f"/repos/{owner}/{repo}/issues",
                json={"title": payload["title"], "body": payload.get("body", "")},
            )
            data = resp.json()
            return {
                "status": "ok",
                "platform": "github",
                "action": action,
                "simulated": False,
                "issue_number": data["number"],
                "url": data["html_url"],
            }

        if action == "create_pr":
            resp = await self._http._request(
                "POST",
                f"/repos/{owner}/{repo}/pulls",
                json={
                    "title": payload["title"],
                    "head": payload["head"],
                    "base": payload.get("base", "main"),
                    "body": payload.get("body", ""),
                },
            )
            data = resp.json()
            return {
                "status": "ok",
                "platform": "github",
                "action": action,
                "simulated": False,
                "pr_number": data["number"],
                "url": data["html_url"],
            }

        if action == "add_comment":
            issue_number = payload["issue_number"]
            resp = await self._http._request(
                "POST",
                f"/repos/{owner}/{repo}/issues/{issue_number}/comments",
                json={"body": payload["body"]},
            )
            data = resp.json()
            return {
                "status": "ok",
                "platform": "github",
                "action": action,
                "simulated": False,
                "comment_id": data["id"],
                "url": data["html_url"],
            }

        if action == "list_prs":
            resp = await self._http._request(
                "GET",
                f"/repos/{owner}/{repo}/pulls",
                params={
                    "state": payload.get("state", "open"),
                    "per_page": payload.get("limit", 10),
                },
            )
            return {
                "status": "ok",
                "platform": "github",
                "action": action,
                "simulated": False,
                "items": [
                    {"number": pr["number"], "title": pr["title"], "state": pr["state"]}
                    for pr in resp.json()
                ],
            }

        return {"status": "error", "platform": "github", "message": f"Unknown action: {action}"}

    async def read(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        log.info("github.read", query=query, limit=limit)
        resp = await self._http._request(
            "GET",
            "/search/issues",
            params={"q": f"{query} repo:{self._owner}/{self._repo}", "per_page": limit},
        )
        items: list[dict[str, Any]] = []
        for item in resp.json().get("items", []):
            items.append(
                {
                    "id": f"{'pr' if 'pull_request' in item else 'issue'}_{item['number']}",
                    "title": item["title"],
                    "state": item["state"],
                    "url": item["html_url"],
                }
            )
        return items

    def available_actions(self) -> list[str]:
        return ["create_issue", "create_pr", "list_prs", "add_comment"]

    async def close(self) -> None:
        await self._http.close()
