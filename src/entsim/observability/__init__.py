"""Observability: lifecycle hooks and in-memory metrics collection."""

from __future__ import annotations

from entsim.observability.hooks import HookRegistry
from entsim.observability.metrics import MetricsCollector

__all__ = ["HookRegistry", "MetricsCollector"]
