"""LLM router: wraps litellm.Router with tier-based model dispatch."""

from __future__ import annotations

from typing import Any

import litellm
import structlog
from litellm import Router

from entsim.llm.models import CompletionRequest, CompletionResponse, LLMTier
from entsim.llm.settings import LLMSettings

logger: structlog.BoundLogger = structlog.get_logger(__name__)

# Mapping from LLMTier to the model-group name used in the Router model list.
_TIER_GROUP: dict[LLMTier, str] = {
    LLMTier.ROUTINE: "routine",
    LLMTier.STANDARD: "standard",
    LLMTier.COMPLEX: "complex",
}


class LLMRouter:
    """Tiered LLM completion router backed by litellm.Router.

    Each tier maps to a named model group in the underlying router.
    Actual model identifiers are resolved from *settings* so they can be
    overridden via environment variables without touching code.
    """

    def __init__(self, settings: LLMSettings | None = None) -> None:
        self._settings = settings or LLMSettings()
        model_list: list[dict[str, Any]] = [
            {
                "model_name": "routine",
                "litellm_params": {"model": self._settings.routine_model},
            },
            {
                "model_name": "standard",
                "litellm_params": {"model": self._settings.standard_model},
            },
            {
                "model_name": "complex",
                "litellm_params": {"model": self._settings.complex_model},
            },
        ]
        self._router = Router(model_list=model_list)

    @property
    def settings(self) -> LLMSettings:
        return self._settings

    def tier_model_name(self, tier: LLMTier) -> str:
        """Return the configured model identifier for *tier*."""
        mapping = {
            LLMTier.ROUTINE: self._settings.routine_model,
            LLMTier.STANDARD: self._settings.standard_model,
            LLMTier.COMPLEX: self._settings.complex_model,
        }
        return mapping[tier]

    async def complete(
        self,
        tier: LLMTier,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> CompletionResponse:
        """Send a chat-completion request to the model group for *tier*.

        Args:
            tier: Determines which model group (and therefore which model) is
                  used for the request.
            messages: OpenAI-compatible chat messages list.
            tools: Optional tool definitions in OpenAI function-calling format.

        Returns:
            A :class:`CompletionResponse` with token counts and cost.
        """
        group = _TIER_GROUP[tier]
        kwargs: dict[str, Any] = {"model": group, "messages": messages}
        if tools:
            kwargs["tools"] = tools

        log = logger.bind(tier=tier.value, model_group=group)
        log.debug("llm_request_start")

        raw = await self._router.acompletion(**kwargs)

        model_used: str = getattr(raw, "model", group)
        usage = getattr(raw, "usage", None)
        input_tokens: int = int(getattr(usage, "prompt_tokens", 0)) if usage else 0
        output_tokens: int = int(getattr(usage, "completion_tokens", 0)) if usage else 0

        try:
            cost: float = float(litellm.completion_cost(completion_response=raw))
        except Exception:
            log.warning("llm_cost_calculation_failed", model_group=group)
            cost = 0.0

        choices = getattr(raw, "choices", [])
        content: str = ""
        if choices:
            message = getattr(choices[0], "message", None)
            if message is not None:
                content = str(getattr(message, "content", "") or "")

        response = CompletionResponse(
            tier=tier,
            model=model_used,
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
        )

        log.info(
            "llm_request_complete",
            model=model_used,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
        )
        return response

    async def complete_request(self, request: CompletionRequest) -> CompletionResponse:
        """Convenience wrapper accepting a :class:`CompletionRequest`."""
        return await self.complete(
            tier=request.tier,
            messages=request.messages,
            tools=request.tools,
        )
