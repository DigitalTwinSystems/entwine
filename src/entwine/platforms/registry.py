"""PlatformRegistry: central catalogue of available platform adapters."""

from __future__ import annotations

import structlog

from entwine.platforms.base import PlatformAdapter

log = structlog.get_logger(__name__)


class PlatformRegistry:
    """Thread-safe registry that maps platform names to adapter instances."""

    def __init__(self) -> None:
        self._adapters: dict[str, PlatformAdapter] = {}

    def register(self, adapter: PlatformAdapter) -> None:
        """Register an adapter.  Raises ``ValueError`` on duplicate names."""
        name = adapter.platform_name
        if name in self._adapters:
            raise ValueError(f"Platform '{name}' is already registered.")
        self._adapters[name] = adapter
        log.info("registry.registered", platform=name)

    def get(self, platform_name: str) -> PlatformAdapter:
        """Return the adapter for *platform_name*.  Raises ``KeyError`` if unknown."""
        try:
            return self._adapters[platform_name]
        except KeyError:
            raise KeyError(f"Unknown platform: '{platform_name}'") from None

    def list_platforms(self) -> list[str]:
        """Return sorted list of registered platform names."""
        return sorted(self._adapters)

    def list_all_actions(self) -> dict[str, list[str]]:
        """Return ``{platform_name: [actions]}`` for every registered adapter."""
        return {
            name: adapter.available_actions() for name, adapter in sorted(self._adapters.items())
        }
