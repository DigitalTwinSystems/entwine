"""HookRegistry: singleton-style callback registry for lifecycle events."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import structlog

log = structlog.get_logger(__name__)

# Supported hook types.
HOOK_AGENT_START = "agent_start"
HOOK_AGENT_STOP = "agent_stop"
HOOK_AGENT_PAUSE = "agent_pause"
HOOK_AGENT_ERROR = "agent_error"
HOOK_LLM_START = "llm_start"
HOOK_LLM_END = "llm_end"
HOOK_TOOL_START = "tool_start"
HOOK_TOOL_END = "tool_end"
HOOK_MESSAGE_SENT = "message_sent"
HOOK_MEMORY_WRITE = "memory_write"

ALL_HOOK_TYPES: frozenset[str] = frozenset(
    {
        HOOK_AGENT_START,
        HOOK_AGENT_STOP,
        HOOK_AGENT_PAUSE,
        HOOK_AGENT_ERROR,
        HOOK_LLM_START,
        HOOK_LLM_END,
        HOOK_TOOL_START,
        HOOK_TOOL_END,
        HOOK_MESSAGE_SENT,
        HOOK_MEMORY_WRITE,
    }
)


class HookRegistry:
    """Registry of callbacks for simulation lifecycle events.

    Callbacks may be synchronous or asynchronous; the registry inspects each
    callback with :func:`asyncio.iscoroutinefunction` and awaits when needed.
    """

    def __init__(self) -> None:
        self._hooks: dict[str, list[Callable[..., Any]]] = {}

    def register(self, hook_type: str, callback: Callable[..., Any]) -> None:
        """Register *callback* to be invoked whenever *hook_type* is emitted."""
        self._hooks.setdefault(hook_type, []).append(callback)
        log.debug("hook.registered", hook_type=hook_type, callback=callback.__name__)

    async def emit(self, hook_type: str, **kwargs: Any) -> None:
        """Invoke all callbacks registered for *hook_type*.

        Unknown hook types are silently ignored (no error, no callbacks).
        Each invocation is logged via structlog.
        """
        callbacks = self._hooks.get(hook_type)
        if not callbacks:
            return

        log.debug("hook.emit", hook_type=hook_type, num_callbacks=len(callbacks), **kwargs)

        for cb in callbacks:
            if asyncio.iscoroutinefunction(cb):
                await cb(**kwargs)
            else:
                cb(**kwargs)
