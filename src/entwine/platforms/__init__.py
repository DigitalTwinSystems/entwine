"""entwine.platforms — platform adapters and registry."""

from entwine.platforms.base import PlatformAdapter
from entwine.platforms.factory import build_platform_registry
from entwine.platforms.registry import PlatformRegistry

__all__ = [
    "PlatformAdapter",
    "PlatformRegistry",
    "build_platform_registry",
]
