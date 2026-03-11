"""Simulation engine orchestrator: wires up all subsystems and drives the tick loop."""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

import structlog

from entwine.agents.models import AgentPersona
from entwine.agents.standard import StandardAgent
from entwine.agents.supervisor import Supervisor
from entwine.config.models import FullConfig
from entwine.events.bus import EventBus
from entwine.events.models import SystemEvent, TaskAssigned
from entwine.observability.cost_tracker import CostTracker
from entwine.platforms.factory import build_platform_registry
from entwine.platforms.registry import PlatformRegistry
from entwine.simulation.clock import SimulationClock
from entwine.tools.builtin import (
    create_github_issue,
    create_pr,
    delegate_task,
    draft_email,
    post_to_linkedin,
    post_to_slack,
    post_to_x,
    query_knowledge,
    read_company_metrics,
    read_crm,
    schedule_meeting,
    set_knowledge_store,
    update_crm_ticket,
)
from entwine.tools.dispatcher import ToolDispatcher

try:
    from entwine.llm.router import LLMRouter
except Exception:  # pragma: no cover
    LLMRouter = None  # type: ignore[assignment,misc]

log = structlog.get_logger(__name__)

# Tool names that indicate a CoderAgent should be used.
_CODER_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "create_github_issue",
        "create_pr",
        "run_code",
        "execute_code",
        "write_code",
        "review_code",
    }
)


def _build_tool_dispatcher() -> ToolDispatcher:
    """Create a ToolDispatcher pre-loaded with built-in tools."""
    dispatcher = ToolDispatcher()
    dispatcher.register(
        name="delegate_task",
        handler=delegate_task,
        description="Delegate a task to another agent.",
        parameters={
            "type": "object",
            "properties": {
                "recipient": {"type": "string"},
                "task_description": {"type": "string"},
                "priority": {"type": "string", "default": "normal"},
            },
            "required": ["recipient", "task_description"],
        },
    )
    dispatcher.register(
        name="query_knowledge",
        handler=query_knowledge,
        description="Query the knowledge base for information relevant to a role.",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "role": {"type": "string"},
            },
            "required": ["query", "role"],
        },
    )
    dispatcher.register(
        name="read_company_metrics",
        handler=read_company_metrics,
        description="Read current company and simulation metrics.",
        parameters={"type": "object", "properties": {}},
    )
    dispatcher.register(
        name="schedule_meeting",
        handler=schedule_meeting,
        description="Schedule a meeting with specified attendees.",
        parameters={
            "type": "object",
            "properties": {
                "attendees": {"type": "string"},
                "time": {"type": "string"},
                "agenda": {"type": "string"},
            },
            "required": ["attendees", "time", "agenda"],
        },
    )
    dispatcher.register(
        name="draft_email",
        handler=draft_email,
        description="Draft an email message.",
        parameters={
            "type": "object",
            "properties": {
                "to": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
            },
            "required": ["to", "subject", "body"],
        },
    )
    dispatcher.register(
        name="post_to_slack",
        handler=post_to_slack,
        description="Post a message to a Slack channel.",
        parameters={
            "type": "object",
            "properties": {
                "channel": {"type": "string"},
                "message": {"type": "string"},
            },
            "required": ["channel", "message"],
        },
    )
    dispatcher.register(
        name="post_to_linkedin",
        handler=post_to_linkedin,
        description="Publish a post to LinkedIn.",
        parameters={
            "type": "object",
            "properties": {
                "content": {"type": "string"},
            },
            "required": ["content"],
        },
    )
    dispatcher.register(
        name="post_to_x",
        handler=post_to_x,
        description="Publish a post to X (Twitter).",
        parameters={
            "type": "object",
            "properties": {
                "content": {"type": "string"},
            },
            "required": ["content"],
        },
    )
    dispatcher.register(
        name="create_github_issue",
        handler=create_github_issue,
        description="Create a GitHub issue.",
        parameters={
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "body": {"type": "string"},
                "labels": {"type": "string", "default": ""},
            },
            "required": ["title", "body"],
        },
    )
    dispatcher.register(
        name="create_pr",
        handler=create_pr,
        description="Create a GitHub pull request.",
        parameters={
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "body": {"type": "string"},
                "branch": {"type": "string"},
            },
            "required": ["title", "body", "branch"],
        },
    )
    dispatcher.register(
        name="read_crm",
        handler=read_crm,
        description="Query the CRM system for customer or deal information.",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
            },
            "required": ["query"],
        },
    )
    dispatcher.register(
        name="update_crm_ticket",
        handler=update_crm_ticket,
        description="Update the status of a CRM ticket.",
        parameters={
            "type": "object",
            "properties": {
                "ticket_id": {"type": "string"},
                "status": {"type": "string"},
                "note": {"type": "string", "default": ""},
            },
            "required": ["ticket_id", "status"],
        },
    )
    return dispatcher


def _build_platform_registry() -> PlatformRegistry:
    """Create a PlatformRegistry with best-available adapters (real or stub)."""
    return build_platform_registry()


def _is_coder_persona(persona: AgentPersona) -> bool:
    """Return True if the persona's tools suggest a CoderAgent."""
    return bool(set(persona.tools) & _CODER_TOOL_NAMES)


class SimulationEngine:
    """Top-level orchestrator that owns every subsystem and drives the simulation.

    Instantiate with a validated :class:`FullConfig`, then call :meth:`start`
    to begin the simulation loop and :meth:`stop` to tear everything down.
    """

    def __init__(
        self,
        config: FullConfig,
        *,
        llm_router: LLMRouter | None = None,
    ) -> None:
        self._config = config
        self._llm_router = llm_router

        # Shared subsystems.
        self._event_bus = EventBus()
        self._clock = SimulationClock(
            tick_interval_seconds=config.simulation.tick_interval_seconds,
        )
        self._tool_dispatcher = _build_tool_dispatcher()
        self._platform_registry = _build_platform_registry()
        self._cost_tracker = CostTracker(
            global_budget=config.simulation.global_budget_usd,
            per_agent_budget=config.simulation.per_agent_budget_usd,
        )

        # Shared mutable world state protected by an asyncio lock.
        self._world_state: dict[str, Any] = {}
        self._world_state_lock = asyncio.Lock()

        # Wire KnowledgeStore for query_knowledge tool (best-effort).
        try:
            from entwine.rag.store import KnowledgeStore as _KS

            set_knowledge_store(_KS())
        except Exception:
            pass

        # Build agents from config.
        self._agents = self._create_agents(config.agents)

        # Supervisor manages all agent lifecycles.
        self._supervisor = Supervisor(agents=self._agents)

        # Background tick task handle.
        self._tick_task: asyncio.Task[None] | None = None

        log.info(
            "engine.created",
            simulation=config.simulation.name,
            agent_count=len(self._agents),
        )

    # ------------------------------------------------------------------
    # Agent construction
    # ------------------------------------------------------------------

    def _build_org_context(self, persona: AgentPersona) -> str:
        """Build org-context string for an agent from enterprise config."""
        enterprise = self._config.enterprise
        parts: list[str] = []

        # Find manager and direct reports from reporting lines.
        manager = None
        reports: list[str] = []
        for line in enterprise.reporting_lines:
            if line.subordinate == persona.name:
                manager = line.manager
            if line.manager == persona.name:
                reports.append(line.subordinate)

        if manager:
            parts.append(f"Reports to: {manager}")
        if reports:
            parts.append(f"Direct reports: {', '.join(reports)}")

        # Find department head.
        for dept in enterprise.departments:
            if dept.name == persona.department and dept.head and dept.head != persona.name:
                parts.append(f"Department head: {dept.head}")
                break

        if enterprise.cross_department_channels:
            parts.append(f"Cross-dept channels: {', '.join(enterprise.cross_department_channels)}")

        return "; ".join(parts)

    def _create_agents(self, personas: list[AgentPersona]) -> list[StandardAgent]:
        """Instantiate agents from persona configs.

        All agents currently use StandardAgent.  CoderAgent selection is
        reserved for when code-execution tools are available.
        """
        agents: list[StandardAgent] = []
        queue: asyncio.Queue[Any] = asyncio.Queue()

        for persona in personas:
            agent = StandardAgent(
                persona=persona,
                event_bus=queue,
                llm_router=self._llm_router,
                tool_dispatcher=self._tool_dispatcher,
                cost_tracker=self._cost_tracker,
                tick_interval=0.05,
            )
            # Inject org context into the agent's world context.
            org_ctx = self._build_org_context(persona)
            if org_ctx:
                agent._org_context = org_ctx
            # Wire up the typed EventBus for pub/sub routing.
            agent._typed_bus = self._event_bus
            agent._inbox = asyncio.Queue()
            agents.append(agent)

        return agents

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start every subsystem and begin the tick loop."""
        await self._event_bus.start()

        # Subscribe all agents to the bus so they receive events.
        for agent in self._agents:
            agent.subscribe_all()

        await self._supervisor.start_all()
        self._clock.start()

        # Launch the background tick loop.
        self._tick_task = asyncio.get_running_loop().create_task(
            self._tick_loop(), name="engine:tick_loop"
        )

        # Seed each agent with an initial task so they start working.
        for agent in self._agents:
            await self._event_bus.publish(
                TaskAssigned(
                    source_agent="simulation",
                    payload={
                        "task": (
                            f"You are starting your workday at {self._config.enterprise.name}. "
                            f"Review your goals and decide what to work on first. "
                            f"Think about what actions you should take given your role."
                        ),
                        "target_agent": agent.name,
                    },
                )
            )

        log.info("engine.started", simulation=self._config.simulation.name)

    async def stop(self) -> None:
        """Shut down the tick loop and every subsystem in reverse order."""
        # Cancel tick loop.
        if self._tick_task is not None and not self._tick_task.done():
            self._tick_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._tick_task
            self._tick_task = None

        self._clock.stop()
        await self._supervisor.stop_all()
        await self._event_bus.stop()

        log.info("engine.stopped", simulation=self._config.simulation.name)

    async def pause(self) -> None:
        """Pause all agents and the clock."""
        for agent in self._agents:
            await agent.pause()
        self._clock.stop()
        log.info("engine.paused")

    async def resume(self) -> None:
        """Resume all agents and the clock."""
        self._clock.start()
        for agent in self._agents:
            await agent.resume()
        log.info("engine.resumed")

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        """Return True if the clock is running."""
        return self._clock.is_running

    @property
    def agent_count(self) -> int:
        """Return the number of agents in the simulation."""
        return len(self._agents)

    @property
    def elapsed_ticks(self) -> int:
        """Return the number of elapsed simulation ticks."""
        return self._clock.elapsed_ticks

    @property
    def world_state(self) -> dict[str, Any]:
        """Return a reference to the shared world state dict."""
        return self._world_state

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    @property
    def cost_tracker(self) -> CostTracker:
        """Return the cost tracker instance."""
        return self._cost_tracker

    def get_status(self) -> dict[str, Any]:
        """Return a snapshot of the simulation status."""
        return {
            "simulation_name": self._config.simulation.name,
            "is_running": self.is_running,
            "elapsed_ticks": self.elapsed_ticks,
            "agent_count": self.agent_count,
            "agents": {
                agent.name: {
                    "state": agent.state.value,
                    "role": agent.persona.role,
                }
                for agent in self._agents
            },
            "clock": {
                "current_time": self._clock.current_time.isoformat(),
                "is_running": self._clock.is_running,
            },
            "platforms": self._platform_registry.list_platforms(),
            "costs": self._cost_tracker.snapshot(),
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _tick_loop(self) -> None:
        """Background coroutine that drives the simulation clock at real-time intervals."""
        interval = self._config.simulation.tick_interval_seconds
        max_ticks = self._config.simulation.max_ticks

        while True:
            await asyncio.sleep(interval)
            if not self._clock.is_running:
                continue
            self._clock.tick()

            # Publish a tick event so agents know time is passing.
            await self._event_bus.publish(
                SystemEvent(
                    source_agent="simulation",
                    payload={
                        "tick": self._clock.elapsed_ticks,
                        "sim_time": self._clock.current_time.isoformat(),
                    },
                )
            )

            if self._cost_tracker.budget_exceeded:
                log.warning(
                    "engine.budget_exceeded",
                    scope=self._cost_tracker.budget_exceeded_scope,
                    cost=self._cost_tracker.global_cost,
                )
                await self.pause()
                break

            if max_ticks is not None and self._clock.elapsed_ticks >= max_ticks:
                log.info("engine.max_ticks_reached", ticks=self._clock.elapsed_ticks)
                break
