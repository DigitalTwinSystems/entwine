"""PlatformClient: shared HTTP base with rate limiting and exponential backoff."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx
import structlog

log = structlog.get_logger(__name__)

# Default retry configuration.
_MAX_RETRIES = 3
_BACKOFF_BASE = 1.0
_BACKOFF_MAX = 30.0


class RateLimiter:
    """Async token-bucket rate limiter.

    *max_calls* per *period_seconds* window. Uses a sliding-window approach
    backed by a simple timestamp deque.
    """

    def __init__(self, max_calls: int, period_seconds: float) -> None:
        self._max_calls = max_calls
        self._period = period_seconds
        self._timestamps: list[float] = []
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            # Purge expired timestamps.
            cutoff = now - self._period
            self._timestamps = [t for t in self._timestamps if t > cutoff]

            if len(self._timestamps) >= self._max_calls:
                # Wait until the oldest entry expires.
                sleep_for = self._timestamps[0] - cutoff
                if sleep_for > 0:
                    log.debug("rate_limiter.waiting", sleep=round(sleep_for, 2))
                    await asyncio.sleep(sleep_for)
                self._timestamps = [
                    t for t in self._timestamps if t > time.monotonic() - self._period
                ]

            self._timestamps.append(time.monotonic())


class PlatformClient:
    """Thin async HTTP wrapper with rate limiting and retries.

    Subclasses should call :meth:`_request` for all API calls.
    """

    def __init__(
        self,
        *,
        base_url: str = "",
        rate_limiter: RateLimiter | None = None,
        headers: dict[str, str] | None = None,
        max_retries: int = _MAX_RETRIES,
    ) -> None:
        self._base_url = base_url
        self._rate_limiter = rate_limiter
        self._max_retries = max_retries
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers=headers or {},
            timeout=30.0,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """Execute an HTTP request with rate limiting and exponential backoff."""
        if self._rate_limiter:
            await self._rate_limiter.acquire()

        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                resp = await self._client.request(method, path, json=json, params=params, data=data)
                if resp.status_code == 429:
                    retry_after = _parse_retry_after(resp)
                    log.warning(
                        "platform_client.rate_limited",
                        path=path,
                        retry_after=retry_after,
                        attempt=attempt,
                    )
                    await asyncio.sleep(retry_after)
                    continue
                resp.raise_for_status()
                return resp
            except (httpx.HTTPStatusError, httpx.TransportError) as exc:
                last_exc = exc
                if attempt < self._max_retries:
                    delay = min(_BACKOFF_BASE * (2**attempt), _BACKOFF_MAX)
                    log.warning(
                        "platform_client.retry",
                        path=path,
                        attempt=attempt,
                        delay=delay,
                        error=str(exc),
                    )
                    await asyncio.sleep(delay)
        raise last_exc  # type: ignore[misc]


def _parse_retry_after(resp: httpx.Response) -> float:
    """Extract wait time from Retry-After or X-RateLimit-Reset headers."""
    if val := resp.headers.get("retry-after"):
        try:
            return float(val)
        except ValueError:
            pass
    if val := resp.headers.get("x-ratelimit-reset"):
        try:
            reset_at = float(val)
            return max(reset_at - time.time(), 1.0)
        except ValueError:
            pass
    return 5.0
