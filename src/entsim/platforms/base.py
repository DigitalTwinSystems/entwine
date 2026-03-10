"""PlatformAdapter: abstract base class for all platform integrations."""

from __future__ import annotations

from abc import ABC, abstractmethod


class PlatformAdapter(ABC):
    """Abstract base class that every platform adapter must implement.

    Subclasses represent a single external platform (X, LinkedIn, GitHub, etc.)
    and expose a uniform send/read interface so that agents can interact with
    any platform through the same contract.
    """

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """Return the unique identifier for this platform (e.g. ``"x"``)."""
        ...

    @abstractmethod
    async def send(self, action: str, payload: dict) -> dict:
        """Execute *action* on the platform with the given *payload*.

        Returns a result dict whose shape is adapter-specific.
        """
        ...

    @abstractmethod
    async def read(self, query: str, limit: int = 10) -> list[dict]:
        """Read items from the platform matching *query*.

        Returns up to *limit* synthetic or real items.
        """
        ...

    @abstractmethod
    def available_actions(self) -> list[str]:
        """Return the list of action names this adapter supports."""
        ...
