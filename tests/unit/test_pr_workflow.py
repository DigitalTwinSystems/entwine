"""Tests for entwine.agents.pr_workflow — PR workflow coordination."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from entwine.agents.pr_workflow import (
    PRWorkflowError,
    handle_ci_failure,
    open_pr,
    publish_ci_result,
    publish_pr_opened,
    run_pr_workflow,
    simulate_ci,
)
from entwine.events.models import CIResult, PROpened, ReviewComplete

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_adapter() -> AsyncMock:
    """Create a mock GitHub adapter."""
    adapter = AsyncMock()
    adapter.send = AsyncMock(
        return_value={
            "status": "ok",
            "platform": "github",
            "action": "create_pr",
            "simulated": False,
            "pr_number": 42,
            "url": "https://github.com/acme/repo/pull/42",
        }
    )
    return adapter


def _make_mock_bus() -> AsyncMock:
    """Create a mock EventBus."""
    bus = AsyncMock()
    bus.publish = AsyncMock()
    return bus


# ---------------------------------------------------------------------------
# Event model tests
# ---------------------------------------------------------------------------


class TestEventModels:
    def test_pr_opened_event(self) -> None:
        evt = PROpened(
            source_agent="coder-1",
            payload={
                "pr_number": 42,
                "pr_url": "https://example.com/pr/42",
                "branch": "feat/x",
                "title": "Add feature",
            },
        )
        assert evt.event_type == "pr_opened"
        assert evt.payload["pr_number"] == 42

    def test_ci_result_event(self) -> None:
        evt = CIResult(
            source_agent="ci-stub",
            payload={"pr_number": 42, "passed": True, "output": "All checks passed."},
        )
        assert evt.event_type == "ci_result"
        assert evt.payload["passed"] is True

    def test_review_complete_event(self) -> None:
        evt = ReviewComplete(
            source_agent="qa-1",
            payload={"pr_number": 42, "approved": True, "comments": []},
        )
        assert evt.event_type == "review_complete"


# ---------------------------------------------------------------------------
# open_pr tests
# ---------------------------------------------------------------------------


class TestOpenPR:
    async def test_opens_pr_via_adapter(self) -> None:
        adapter = _make_mock_adapter()
        result = await open_pr(adapter, branch="feat/new", title="Add feature", body="Description")

        adapter.send.assert_awaited_once_with(
            "create_pr",
            {"title": "Add feature", "head": "feat/new", "base": "main", "body": "Description"},
        )
        assert result["pr_number"] == 42
        assert result["url"] == "https://github.com/acme/repo/pull/42"

    async def test_opens_pr_with_custom_base(self) -> None:
        adapter = _make_mock_adapter()
        await open_pr(adapter, branch="feat/x", title="Fix", base="develop")

        adapter.send.assert_awaited_once_with(
            "create_pr",
            {"title": "Fix", "head": "feat/x", "base": "develop", "body": ""},
        )

    async def test_raises_on_invalid_adapter_response(self) -> None:
        adapter = AsyncMock()
        adapter.send = AsyncMock(return_value={"status": "error", "message": "unauthorized"})
        with pytest.raises(PRWorkflowError, match="invalid PR result"):
            await open_pr(adapter, branch="feat/x", title="Fix")


# ---------------------------------------------------------------------------
# publish_pr_opened tests
# ---------------------------------------------------------------------------


class TestPublishPROpened:
    async def test_publishes_event(self) -> None:
        bus = _make_mock_bus()
        await publish_pr_opened(
            bus,
            source_agent="coder-1",
            pr_number=42,
            pr_url="https://example.com/pr/42",
            branch="feat/x",
            title="Add feature",
        )

        bus.publish.assert_awaited_once()
        event = bus.publish.call_args[0][0]
        assert isinstance(event, PROpened)
        assert event.payload["pr_number"] == 42
        assert event.source_agent == "coder-1"


# ---------------------------------------------------------------------------
# simulate_ci tests
# ---------------------------------------------------------------------------


class TestSimulateCI:
    async def test_ci_passes_by_default(self) -> None:
        result = await simulate_ci(pr_number=42)
        assert isinstance(result, CIResult)
        assert result.payload["passed"] is True
        assert result.payload["pr_number"] == 42

    async def test_ci_always_fails_with_rate_1(self) -> None:
        result = await simulate_ci(pr_number=42, fail_rate=1.0)
        assert result.payload["passed"] is False
        assert "failed" in result.payload["output"]

    async def test_ci_result_source_is_ci_stub(self) -> None:
        result = await simulate_ci(pr_number=10)
        assert result.source_agent == "ci-stub"


# ---------------------------------------------------------------------------
# publish_ci_result tests
# ---------------------------------------------------------------------------


class TestPublishCIResult:
    async def test_publishes_ci_event(self) -> None:
        bus = _make_mock_bus()
        ci_result = CIResult(
            source_agent="ci-stub",
            payload={"pr_number": 42, "passed": True, "output": "ok"},
        )
        await publish_ci_result(bus, ci_result)
        bus.publish.assert_awaited_once_with(ci_result)


# ---------------------------------------------------------------------------
# handle_ci_failure tests
# ---------------------------------------------------------------------------


class TestHandleCIFailure:
    async def test_calls_on_fix_callback(self) -> None:
        ci_result = CIResult(
            source_agent="ci-stub",
            payload={"pr_number": 42, "passed": False, "output": "test_main.py FAILED"},
        )
        on_fix = AsyncMock(return_value="fixed code")
        result = await handle_ci_failure(ci_result, on_fix=on_fix)

        on_fix.assert_awaited_once_with("test_main.py FAILED")
        assert result == "fixed code"

    async def test_returns_none_without_callback(self) -> None:
        ci_result = CIResult(
            source_agent="ci-stub",
            payload={"pr_number": 42, "passed": False, "output": "FAILED"},
        )
        result = await handle_ci_failure(ci_result)
        assert result is None


# ---------------------------------------------------------------------------
# run_pr_workflow tests
# ---------------------------------------------------------------------------


class TestRunPRWorkflow:
    async def test_full_workflow_success(self) -> None:
        adapter = _make_mock_adapter()
        bus = _make_mock_bus()

        result = await run_pr_workflow(
            adapter,
            bus,
            source_agent="coder-1",
            branch="feat/new",
            title="Add feature",
            body="Description",
        )

        assert result["pr_number"] == 42
        assert result["ci_passed"] is True
        # Should have published PROpened + CIResult = 2 events
        assert bus.publish.await_count == 2

    async def test_workflow_with_ci_failure_retries(self) -> None:
        adapter = _make_mock_adapter()
        bus = _make_mock_bus()

        result = await run_pr_workflow(
            adapter,
            bus,
            source_agent="coder-1",
            branch="feat/bugfix",
            title="Fix bug",
            ci_fail_rate=1.0,  # Always fail
            max_ci_iterations=3,
        )

        assert result["ci_passed"] is False
        # PROpened + 3 CIResults = 4 events
        assert bus.publish.await_count == 4

    async def test_workflow_respects_max_iterations(self) -> None:
        adapter = _make_mock_adapter()
        bus = _make_mock_bus()

        await run_pr_workflow(
            adapter,
            bus,
            source_agent="coder-1",
            branch="feat/x",
            title="Test",
            ci_fail_rate=1.0,
            max_ci_iterations=1,
        )

        # PROpened + 1 CIResult = 2 events
        assert bus.publish.await_count == 2

    async def test_workflow_calls_on_ci_failure(self) -> None:
        adapter = _make_mock_adapter()
        bus = _make_mock_bus()
        on_fix = AsyncMock(return_value="fix applied")

        await run_pr_workflow(
            adapter,
            bus,
            source_agent="coder-1",
            branch="feat/bugfix",
            title="Fix bug",
            ci_fail_rate=1.0,
            max_ci_iterations=2,
            on_ci_failure=on_fix,
        )

        # on_fix should be called on each CI failure
        assert on_fix.await_count == 2

    async def test_workflow_returns_simulated_flag(self) -> None:
        adapter = _make_mock_adapter()
        bus = _make_mock_bus()

        result = await run_pr_workflow(
            adapter,
            bus,
            source_agent="coder-1",
            branch="feat/x",
            title="Test",
        )

        assert result["simulated"] is False
