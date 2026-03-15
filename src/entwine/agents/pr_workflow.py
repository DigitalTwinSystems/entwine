"""PR workflow: open PRs, simulate CI, and coordinate review cycle."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING, Any

import structlog

from entwine.events.models import CIResult, PROpened

if TYPE_CHECKING:
    from entwine.events.bus import EventBus
    from entwine.platforms.base import PlatformAdapter

log = structlog.get_logger(__name__)

DEFAULT_MAX_CI_ITERATIONS = 3
DEFAULT_CI_FAIL_RATE = 0.0  # Default: always pass


class PRWorkflowError(Exception):
    """Raised when the PR workflow encounters an unrecoverable error."""


async def open_pr(
    adapter: PlatformAdapter,
    *,
    branch: str,
    title: str,
    body: str = "",
    base: str = "main",
) -> dict[str, Any]:
    """Open a pull request via the GitHub platform adapter."""
    result = await adapter.send(
        "create_pr",
        {
            "title": title,
            "head": branch,
            "base": base,
            "body": body,
        },
    )

    # Validate adapter response
    pr_number = result.get("pr_number", 0)
    if not pr_number or result.get("status") not in ("ok", None):
        raise PRWorkflowError(f"Adapter returned invalid PR result: {result}")

    log.info(
        "pr_workflow.pr_opened",
        pr_number=pr_number,
        url=result.get("url"),
    )
    return result


async def publish_pr_opened(
    bus: EventBus,
    *,
    source_agent: str,
    pr_number: int,
    pr_url: str,
    branch: str,
    title: str,
) -> None:
    """Publish a PROpened event to the event bus."""
    event = PROpened(
        source_agent=source_agent,
        payload={
            "pr_number": pr_number,
            "pr_url": pr_url,
            "branch": branch,
            "title": title,
        },
    )
    await bus.publish(event)


async def simulate_ci(
    *,
    pr_number: int,
    fail_rate: float = DEFAULT_CI_FAIL_RATE,
) -> CIResult:
    """Simulate a CI run (stub). Returns pass or fail based on fail_rate."""
    passed = random.random() >= fail_rate

    output = "All checks passed." if passed else "Test suite failed: 2 failures in test_main.py"

    return CIResult(
        source_agent="ci-stub",
        payload={
            "pr_number": pr_number,
            "passed": passed,
            "output": output,
        },
    )


async def publish_ci_result(bus: EventBus, ci_result: CIResult) -> None:
    """Publish a CIResult event to the event bus."""
    await bus.publish(ci_result)


async def handle_ci_failure(
    ci_result: CIResult,
    *,
    on_fix: Any = None,
) -> str | None:
    """Feed CI failure output back to the coder agent for iteration.

    Args:
        ci_result: The failed CI result with output.
        on_fix: Optional async callable(ci_output: str) -> str that
                triggers a fix cycle (e.g. CoderAgent._call_llm with CI output).

    Returns:
        The fix output from on_fix, or None if no callback provided.
    """
    ci_output = ci_result.payload.get("output", "")
    log.info(
        "pr_workflow.handling_ci_failure",
        pr_number=ci_result.payload.get("pr_number"),
        output=ci_output[:200],
    )

    if on_fix is not None:
        return await on_fix(ci_output)
    return None


async def run_pr_workflow(
    adapter: PlatformAdapter,
    bus: EventBus,
    *,
    source_agent: str,
    branch: str,
    title: str,
    body: str = "",
    ci_fail_rate: float = DEFAULT_CI_FAIL_RATE,
    max_ci_iterations: int = DEFAULT_MAX_CI_ITERATIONS,
    on_ci_failure: Any = None,
) -> dict[str, Any]:
    """Run the full PR workflow: open PR → CI → publish events.

    Args:
        on_ci_failure: Optional async callable(ci_output: str) -> str for
                       feeding CI failures back to the coder for iteration.

    Returns the PR result dict with pr_number, url, ci_passed.
    """
    # Open PR
    pr_result = await open_pr(adapter, branch=branch, title=title, body=body)
    pr_number = pr_result.get("pr_number", 0)
    pr_url = pr_result.get("url", "")

    # Publish PROpened
    await publish_pr_opened(
        bus,
        source_agent=source_agent,
        pr_number=pr_number,
        pr_url=pr_url,
        branch=branch,
        title=title,
    )

    # CI loop
    ci_passed = False
    for iteration in range(max_ci_iterations):
        ci_result = await simulate_ci(pr_number=pr_number, fail_rate=ci_fail_rate)
        await publish_ci_result(bus, ci_result)

        ci_passed = ci_result.payload.get("passed", False)
        if ci_passed:
            log.info("pr_workflow.ci_passed", pr_number=pr_number, iteration=iteration + 1)
            break

        log.warning(
            "pr_workflow.ci_failed",
            pr_number=pr_number,
            iteration=iteration + 1,
            max=max_ci_iterations,
        )

        # Feed CI failure back to coder for iteration
        await handle_ci_failure(ci_result, on_fix=on_ci_failure)

    return {
        "pr_number": pr_number,
        "pr_url": pr_url,
        "ci_passed": ci_passed,
        "simulated": pr_result.get("simulated", True),
    }
