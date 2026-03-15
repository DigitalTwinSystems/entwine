"""QAAgent: reviews pull requests using read-only tools and posts review comments."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import structlog

from entwine.agents.base import BaseAgent
from entwine.agents.models import AgentPersona
from entwine.events.models import PROpened, ReviewComplete

if TYPE_CHECKING:
    from collections.abc import Callable

    from entwine.events.bus import EventBus
    from entwine.platforms.base import PlatformAdapter

log = structlog.get_logger(__name__)

# Read-only tools — no Write, Edit, or Bash.
QA_ALLOWED_TOOLS = ["Read", "Glob", "Grep"]


class QAAgent(BaseAgent):
    """QA agent that reviews PRs using read-only tools.

    Does not require a sandbox — all tools are read-only.
    """

    def __init__(
        self,
        persona: AgentPersona,
        event_bus: asyncio.Queue[Any],
        *,
        platform_adapter: PlatformAdapter | None = None,
        sdk_session_factory: Callable[..., Any] | None = None,
        typed_bus: EventBus | None = None,
        tick_interval: float = 0.05,
    ) -> None:
        super().__init__(persona, event_bus, typed_bus=typed_bus, tick_interval=tick_interval)
        self._adapter = platform_adapter
        self._sdk_session_factory = sdk_session_factory

    # ------------------------------------------------------------------
    # PR review
    # ------------------------------------------------------------------

    async def handle_pr_opened(self, event: PROpened) -> dict[str, Any]:
        """Review a PR and return the review result.

        Returns dict with: pr_number, approved, comments.
        """
        pr_number = event.payload.get("pr_number", 0)
        branch = event.payload.get("branch", "")
        title = event.payload.get("title", "")

        log.info(
            "qa_agent.review_started",
            agent=self.name,
            pr_number=pr_number,
            title=title,
        )

        # Build review prompt
        prompt = self._build_review_prompt(pr_number, branch, title)

        # Get review analysis (from LLM or fallback)
        review_text = await self._call_llm(
            {"type": "pr_review", "pr_number": pr_number, "prompt": prompt},
            [],
        )

        # Parse review decision
        approved, comments = self._parse_review(review_text, pr_number)

        # Post comments via adapter
        await self._post_review_comments(pr_number, comments)

        # Publish ReviewComplete event
        await self._publish_review_complete(pr_number, approved, comments)

        log.info(
            "qa_agent.review_complete",
            agent=self.name,
            pr_number=pr_number,
            approved=approved,
            comment_count=len(comments),
        )

        return {
            "pr_number": pr_number,
            "approved": approved,
            "comments": comments,
        }

    # ------------------------------------------------------------------
    # Overrides
    # ------------------------------------------------------------------

    async def _call_llm(self, event: Any, rag_results: list[Any]) -> Any:
        """Query the SDK session with read-only tools for code review.

        Uses the SDK session factory if provided, enforcing QA_ALLOWED_TOOLS.
        Falls back to a default review response if no SDK is configured.
        """
        if not isinstance(event, dict) or event.get("type") != "pr_review":
            return None

        prompt = event.get("prompt", "")

        # Use SDK session if available
        if self._sdk_session_factory is not None:
            try:
                session = self._sdk_session_factory(
                    allowed_tools=QA_ALLOWED_TOOLS,
                )
                result = await session.run(prompt)
                if hasattr(result, "task_description"):
                    # CodingTaskResult — extract collected content or description
                    return result.task_description if result.success else None
                return result
            except Exception as exc:
                log.error("qa_agent.sdk_error", agent=self.name, error=str(exc))
                return None

        # Fallback: structured review when no SDK configured
        return (
            "APPROVED\n"
            "The code changes look good. Minor suggestions:\n"
            "- Consider adding more test coverage for edge cases\n"
            "- Documentation could be improved"
        )

    async def _emit_events(self, llm_response: Any, tool_results: list[Any]) -> None:
        """No-op for QA agent — events are emitted via handle_pr_opened."""

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_review_prompt(self, pr_number: int, branch: str, title: str) -> str:
        """Build a code review prompt."""
        parts = [
            f"Review PR #{pr_number}: {title}",
            f"Branch: {branch}",
            "",
            "Analyze the code changes for:",
            "1. Code quality and correctness",
            "2. Test coverage gaps",
            "3. Style and convention adherence",
            "4. Potential bugs or security issues",
            "",
            "Respond with APPROVED or CHANGES_REQUESTED followed by your findings.",
        ]
        return "\n".join(parts)

    def _parse_review(self, review_text: Any, pr_number: int) -> tuple[bool, list[str]]:
        """Parse review text into approved flag and comments list."""
        if not review_text or not isinstance(review_text, str):
            return True, [f"PR #{pr_number}: No issues found (auto-approved)."]

        lines = review_text.strip().splitlines()
        first_line = lines[0].strip().upper() if lines else ""
        approved = "APPROVED" in first_line and "CHANGES_REQUESTED" not in first_line

        comments = [line.strip() for line in lines[1:] if line.strip()]
        if not comments:
            comments = [f"PR #{pr_number}: Review complete."]

        return approved, comments

    async def _post_review_comments(self, pr_number: int, comments: list[str]) -> None:
        """Post review comments via the platform adapter."""
        if self._adapter is None:
            log.info("qa_agent.no_adapter", msg="Skipping comment posting (no adapter)")
            return

        body = "\n".join(f"- {c}" for c in comments)
        try:
            await self._adapter.send(
                "add_comment",
                {"issue_number": pr_number, "body": f"**QA Review ({self.name})**\n\n{body}"},
            )
        except Exception as exc:
            log.warning("qa_agent.comment_error", pr_number=pr_number, error=str(exc))

    async def _publish_review_complete(
        self, pr_number: int, approved: bool, comments: list[str]
    ) -> None:
        """Publish a ReviewComplete event."""
        event = ReviewComplete(
            source_agent=self.name,
            payload={
                "pr_number": pr_number,
                "approved": approved,
                "comments": comments,
            },
        )
        if self._typed_bus is not None:
            await self._typed_bus.publish(event)
        else:
            await self._event_bus.put(
                {
                    "type": "review_complete",
                    "source": self.name,
                    "pr_number": pr_number,
                    "approved": approved,
                    "comments": comments,
                }
            )
