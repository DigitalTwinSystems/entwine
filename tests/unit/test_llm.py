"""Unit tests for the LLM integration layer."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from entwine.llm.models import CompletionRequest, CompletionResponse, LLMTier
from entwine.llm.router import LLMRouter
from entwine.llm.settings import LLMSettings

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def make_settings(
    routine: str = "openai/gpt-test-routine",
    standard: str = "openai/gpt-test-standard",
    complex_: str = "openai/gpt-test-complex",
) -> LLMSettings:
    """Return an LLMSettings instance with test model names."""
    return LLMSettings(
        routine_model=routine,
        standard_model=standard,
        complex_model=complex_,
    )


def make_mock_response(
    model: str = "openai/gpt-test-standard",
    content: str = "Hello",
    prompt_tokens: int = 10,
    completion_tokens: int = 5,
) -> MagicMock:
    """Build a MagicMock that mimics a litellm ModelResponse."""
    usage = MagicMock()
    usage.prompt_tokens = prompt_tokens
    usage.completion_tokens = completion_tokens

    message = MagicMock()
    message.content = content

    choice = MagicMock()
    choice.message = message

    response = MagicMock()
    response.model = model
    response.usage = usage
    response.choices = [choice]
    return response


# ---------------------------------------------------------------------------
# LLMSettings tests
# ---------------------------------------------------------------------------


class TestLLMSettings:
    def test_default_model_names(self) -> None:
        """Settings should expose sensible default model names."""
        settings = LLMSettings()
        assert "haiku" in settings.routine_model.lower()
        assert "sonnet" in settings.standard_model.lower()
        assert "opus" in settings.complex_model.lower()

    def test_custom_model_names(self) -> None:
        """Constructor overrides should be reflected in the instance."""
        settings = make_settings()
        assert settings.routine_model == "openai/gpt-test-routine"
        assert settings.standard_model == "openai/gpt-test-standard"
        assert settings.complex_model == "openai/gpt-test-complex"

    def test_env_var_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ENTWINE_LLM_* env vars should override defaults."""
        monkeypatch.setenv("ENTWINE_LLM_ROUTINE_MODEL", "openai/env-routine")
        settings = LLMSettings()
        assert settings.routine_model == "openai/env-routine"


# ---------------------------------------------------------------------------
# LLMRouter initialisation tests
# ---------------------------------------------------------------------------


class TestLLMRouterInit:
    @patch("entwine.llm.router.Router")
    def test_router_initialised_with_three_model_groups(self, mock_router_cls: MagicMock) -> None:
        """Router constructor should receive exactly three model-list entries."""
        settings = make_settings()
        LLMRouter(settings=settings)

        mock_router_cls.assert_called_once()
        call_kwargs: dict[str, Any] = mock_router_cls.call_args.kwargs
        model_list: list[dict[str, Any]] = call_kwargs["model_list"]
        assert len(model_list) == 3

    @patch("entwine.llm.router.Router")
    def test_model_list_entries_use_settings_values(self, mock_router_cls: MagicMock) -> None:
        """Each model-list entry should use the model name from settings."""
        settings = make_settings()
        LLMRouter(settings=settings)

        call_kwargs: dict[str, Any] = mock_router_cls.call_args.kwargs
        model_list: list[dict[str, Any]] = call_kwargs["model_list"]

        by_name = {entry["model_name"]: entry for entry in model_list}
        assert by_name["routine"]["litellm_params"]["model"] == settings.routine_model
        assert by_name["standard"]["litellm_params"]["model"] == settings.standard_model
        assert by_name["complex"]["litellm_params"]["model"] == settings.complex_model

    @patch("entwine.llm.router.Router")
    def test_default_settings_used_when_none_provided(self, mock_router_cls: MagicMock) -> None:
        """LLMRouter should create its own LLMSettings when none is passed."""
        LLMRouter()
        mock_router_cls.assert_called_once()

    @patch("entwine.llm.router.Router")
    def test_settings_property_returns_settings(self, _mock_router_cls: MagicMock) -> None:
        settings = make_settings()
        router = LLMRouter(settings=settings)
        assert router.settings is settings


# ---------------------------------------------------------------------------
# Tier-to-model mapping tests
# ---------------------------------------------------------------------------


class TestTierModelMapping:
    @patch("entwine.llm.router.Router")
    def test_tier_model_name_routine(self, _mock_router_cls: MagicMock) -> None:
        settings = make_settings()
        router = LLMRouter(settings=settings)
        assert router.tier_model_name(LLMTier.ROUTINE) == settings.routine_model

    @patch("entwine.llm.router.Router")
    def test_tier_model_name_standard(self, _mock_router_cls: MagicMock) -> None:
        settings = make_settings()
        router = LLMRouter(settings=settings)
        assert router.tier_model_name(LLMTier.STANDARD) == settings.standard_model

    @patch("entwine.llm.router.Router")
    def test_tier_model_name_complex(self, _mock_router_cls: MagicMock) -> None:
        settings = make_settings()
        router = LLMRouter(settings=settings)
        assert router.tier_model_name(LLMTier.COMPLEX) == settings.complex_model


# ---------------------------------------------------------------------------
# LLMRouter.complete tests — model group dispatch
# ---------------------------------------------------------------------------


class TestLLMRouterComplete:
    """Verify that complete() calls acompletion with the correct model group."""

    def _make_router(self) -> tuple[LLMRouter, MagicMock]:
        """Return (router, mock_inner_router) with acompletion stubbed out."""
        settings = make_settings()
        with patch("entwine.llm.router.Router") as mock_router_cls:
            mock_inner = MagicMock()
            mock_router_cls.return_value = mock_inner
            router = LLMRouter(settings=settings)
        return router, mock_inner

    @pytest.mark.asyncio
    async def test_complete_routine_calls_correct_group(self) -> None:
        router, mock_inner = self._make_router()
        mock_response = make_mock_response(model="openai/gpt-test-routine")
        mock_inner.acompletion = AsyncMock(return_value=mock_response)

        with patch("entwine.llm.router.litellm.completion_cost", return_value=0.001):
            await router.complete(LLMTier.ROUTINE, [{"role": "user", "content": "hi"}])

        mock_inner.acompletion.assert_awaited_once()
        call_kwargs = mock_inner.acompletion.call_args.kwargs
        assert call_kwargs["model"] == "routine"

    @pytest.mark.asyncio
    async def test_complete_standard_calls_correct_group(self) -> None:
        router, mock_inner = self._make_router()
        mock_response = make_mock_response(model="openai/gpt-test-standard")
        mock_inner.acompletion = AsyncMock(return_value=mock_response)

        with patch("entwine.llm.router.litellm.completion_cost", return_value=0.002):
            await router.complete(LLMTier.STANDARD, [{"role": "user", "content": "hi"}])

        call_kwargs = mock_inner.acompletion.call_args.kwargs
        assert call_kwargs["model"] == "standard"

    @pytest.mark.asyncio
    async def test_complete_complex_calls_correct_group(self) -> None:
        router, mock_inner = self._make_router()
        mock_response = make_mock_response(model="openai/gpt-test-complex")
        mock_inner.acompletion = AsyncMock(return_value=mock_response)

        with patch("entwine.llm.router.litellm.completion_cost", return_value=0.005):
            await router.complete(LLMTier.COMPLEX, [{"role": "user", "content": "hi"}])

        call_kwargs = mock_inner.acompletion.call_args.kwargs
        assert call_kwargs["model"] == "complex"

    @pytest.mark.asyncio
    async def test_complete_returns_completion_response(self) -> None:
        router, mock_inner = self._make_router()
        mock_response = make_mock_response(
            model="openai/gpt-test-standard",
            content="Test answer",
            prompt_tokens=20,
            completion_tokens=8,
        )
        mock_inner.acompletion = AsyncMock(return_value=mock_response)

        with patch("entwine.llm.router.litellm.completion_cost", return_value=0.003):
            result = await router.complete(LLMTier.STANDARD, [{"role": "user", "content": "hi"}])

        assert isinstance(result, CompletionResponse)
        assert result.tier == LLMTier.STANDARD
        assert result.content == "Test answer"
        assert result.input_tokens == 20
        assert result.output_tokens == 8
        assert result.cost_usd == pytest.approx(0.003)

    @pytest.mark.asyncio
    async def test_complete_passes_tools_when_provided(self) -> None:
        router, mock_inner = self._make_router()
        mock_response = make_mock_response()
        mock_inner.acompletion = AsyncMock(return_value=mock_response)

        tools = [{"type": "function", "function": {"name": "my_tool", "parameters": {}}}]
        with patch("entwine.llm.router.litellm.completion_cost", return_value=0.001):
            await router.complete(
                LLMTier.STANDARD, [{"role": "user", "content": "hi"}], tools=tools
            )

        call_kwargs = mock_inner.acompletion.call_args.kwargs
        assert call_kwargs["tools"] == tools

    @pytest.mark.asyncio
    async def test_complete_no_tools_kwarg_when_none(self) -> None:
        router, mock_inner = self._make_router()
        mock_response = make_mock_response()
        mock_inner.acompletion = AsyncMock(return_value=mock_response)

        with patch("entwine.llm.router.litellm.completion_cost", return_value=0.001):
            await router.complete(LLMTier.STANDARD, [{"role": "user", "content": "hi"}])

        call_kwargs = mock_inner.acompletion.call_args.kwargs
        assert "tools" not in call_kwargs

    @pytest.mark.asyncio
    async def test_complete_cost_fallback_on_exception(self) -> None:
        """cost_usd should be 0.0 if litellm.completion_cost raises."""
        router, mock_inner = self._make_router()
        mock_response = make_mock_response()
        mock_inner.acompletion = AsyncMock(return_value=mock_response)

        with patch(
            "entwine.llm.router.litellm.completion_cost",
            side_effect=Exception("cost error"),
        ):
            result = await router.complete(LLMTier.ROUTINE, [{"role": "user", "content": "hi"}])

        assert result.cost_usd == 0.0


# ---------------------------------------------------------------------------
# CompletionRequest / CompletionResponse model tests
# ---------------------------------------------------------------------------


class TestModels:
    def test_completion_request_requires_messages(self) -> None:
        req = CompletionRequest(
            tier=LLMTier.ROUTINE,
            messages=[{"role": "user", "content": "hello"}],
        )
        assert req.tier == LLMTier.ROUTINE
        assert req.tools is None

    def test_completion_response_fields(self) -> None:
        resp = CompletionResponse(
            tier=LLMTier.STANDARD,
            model="anthropic/claude-sonnet-4-6",
            content="OK",
            input_tokens=5,
            output_tokens=2,
            cost_usd=0.001,
        )
        assert resp.tier == LLMTier.STANDARD
        assert resp.model == "anthropic/claude-sonnet-4-6"

    def test_llm_tier_values(self) -> None:
        assert LLMTier.ROUTINE.value == "routine"
        assert LLMTier.STANDARD.value == "standard"
        assert LLMTier.COMPLEX.value == "complex"


# ---------------------------------------------------------------------------
# LLMRouter.complete_request — line 128
# ---------------------------------------------------------------------------


class TestCompleteRequest:
    """Verify that complete_request() delegates to complete() correctly."""

    def _make_router(self) -> tuple[LLMRouter, MagicMock]:
        settings = make_settings()
        with patch("entwine.llm.router.Router") as mock_router_cls:
            mock_inner = MagicMock()
            mock_router_cls.return_value = mock_inner
            router = LLMRouter(settings=settings)
        return router, mock_inner

    @pytest.mark.asyncio
    async def test_complete_request_delegates(self) -> None:
        router, mock_inner = self._make_router()
        mock_response = make_mock_response(model="openai/gpt-test-routine")
        mock_inner.acompletion = AsyncMock(return_value=mock_response)

        request = CompletionRequest(
            tier=LLMTier.ROUTINE,
            messages=[{"role": "user", "content": "hello"}],
        )

        with patch("entwine.llm.router.litellm.completion_cost", return_value=0.001):
            result = await router.complete_request(request)

        assert isinstance(result, CompletionResponse)
        assert result.content == "Hello"
        mock_inner.acompletion.assert_awaited_once()
        call_kwargs = mock_inner.acompletion.call_args.kwargs
        assert call_kwargs["model"] == "routine"

    @pytest.mark.asyncio
    async def test_complete_request_with_tools(self) -> None:
        router, mock_inner = self._make_router()
        mock_response = make_mock_response()
        mock_inner.acompletion = AsyncMock(return_value=mock_response)

        tools = [{"type": "function", "function": {"name": "t", "parameters": {}}}]
        request = CompletionRequest(
            tier=LLMTier.STANDARD,
            messages=[{"role": "user", "content": "hi"}],
            tools=tools,
        )

        with patch("entwine.llm.router.litellm.completion_cost", return_value=0.001):
            await router.complete_request(request)

        call_kwargs = mock_inner.acompletion.call_args.kwargs
        assert call_kwargs["tools"] == tools


# ---------------------------------------------------------------------------
# LLMRouter.complete — no usage / no choices edge cases (line 52 fallback)
# ---------------------------------------------------------------------------


class TestCompleteEdgeCases:
    def _make_router(self) -> tuple[LLMRouter, MagicMock]:
        settings = make_settings()
        with patch("entwine.llm.router.Router") as mock_router_cls:
            mock_inner = MagicMock()
            mock_router_cls.return_value = mock_inner
            router = LLMRouter(settings=settings)
        return router, mock_inner

    @pytest.mark.asyncio
    async def test_complete_with_no_usage(self) -> None:
        """When the response has no usage attribute, tokens should be 0."""
        router, mock_inner = self._make_router()
        response = MagicMock()
        response.model = "test"
        response.usage = None
        response.choices = []
        mock_inner.acompletion = AsyncMock(return_value=response)

        with patch("entwine.llm.router.litellm.completion_cost", return_value=0.0):
            result = await router.complete(LLMTier.STANDARD, [{"role": "user", "content": "x"}])

        assert result.input_tokens == 0
        assert result.output_tokens == 0
        assert result.content == ""
