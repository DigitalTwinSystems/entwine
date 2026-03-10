"""Tool dispatcher with a registry for handler functions."""

from __future__ import annotations

import asyncio
import traceback
from collections.abc import Callable
from typing import Any

import structlog

from entwine.tools.models import ToolCall, ToolResult

logger = structlog.get_logger(__name__)


class ToolDispatcher:
    """Registry-based dispatcher that maps tool names to handler functions."""

    def __init__(self) -> None:
        self._handlers: dict[str, Callable[..., Any]] = {}
        self._descriptions: dict[str, str] = {}
        self._parameters: dict[str, dict[str, Any]] = {}

    def register(
        self,
        name: str,
        handler: Callable[..., Any],
        description: str,
        parameters: dict[str, Any],
    ) -> None:
        """Register a tool handler with its metadata."""
        self._handlers[name] = handler
        self._descriptions[name] = description
        self._parameters[name] = parameters
        logger.info("tool_registered", tool_name=name)

    async def dispatch(self, tool_call: ToolCall) -> ToolResult:
        """Execute a single tool call and return its result."""
        logger.info("tool_dispatch_start", tool_name=tool_call.name, call_id=tool_call.call_id)

        handler = self._handlers.get(tool_call.name)
        if handler is None:
            error_msg = f"Unknown tool: {tool_call.name}"
            logger.warning("tool_dispatch_unknown", tool_name=tool_call.name)
            return ToolResult(
                call_id=tool_call.call_id,
                name=tool_call.name,
                output="",
                error=error_msg,
            )

        try:
            if asyncio.iscoroutinefunction(handler):
                result = await handler(**tool_call.arguments)
            else:
                result = handler(**tool_call.arguments)

            logger.info(
                "tool_dispatch_success", tool_name=tool_call.name, call_id=tool_call.call_id
            )
            return ToolResult(
                call_id=tool_call.call_id,
                name=tool_call.name,
                output=str(result),
            )
        except Exception:
            error_msg = traceback.format_exc()
            logger.error(
                "tool_dispatch_error",
                tool_name=tool_call.name,
                call_id=tool_call.call_id,
                error=error_msg,
            )
            return ToolResult(
                call_id=tool_call.call_id,
                name=tool_call.name,
                output="",
                error=error_msg,
            )

    async def dispatch_many(self, tool_calls: list[ToolCall]) -> list[ToolResult]:
        """Dispatch multiple tool calls sequentially."""
        results: list[ToolResult] = []
        for call in tool_calls:
            results.append(await self.dispatch(call))
        return results

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        """Return tool definitions in OpenAI function-calling format."""
        definitions: list[dict[str, Any]] = []
        for name in self._handlers:
            definitions.append(
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": self._descriptions[name],
                        "parameters": self._parameters[name],
                    },
                }
            )
        return definitions
