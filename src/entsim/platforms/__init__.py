"""entsim.platforms — platform adapters and registry."""

from entsim.platforms.base import PlatformAdapter
from entsim.platforms.registry import PlatformRegistry

__all__ = [
    "PlatformAdapter",
    "PlatformRegistry",
]
