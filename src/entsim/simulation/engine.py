"""Simulation engine orchestrator: wires up all subsystems and drives the tick loop."""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

import structlog

from entsim.agents.models import AgentPersona
from entsim.agents.standard import StandardAgent
from entsim.agents.supervisor import Supervisor
from entsim.config.models import FullConfig
from entsim.events.bus import EventBus
from entsim.platforms.registry import PlatformRegistry
from entsim.platforms.stubs import (
    EmailAdapter,
    GitHubAdapter,
    LinkedInAdapter,
    SlackAdapter,
    XAdapter,
)
from entsim.simulation.clock import SimulationClock
from entsim.tools.builtin import delegate_task, query_knowledge, read_metrics
from entsim.tools.dispatcher import ToolDispatcher

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
        name="read_metrics",
        handler=read_metrics,
        description="Read current simulation metrics.",
        parameters={"type": "object", "properties": {}},
    )
    return dispatcher


def _build_platform_registry() -> PlatformRegistry:
    """Create a PlatformRegistry with all stub adapters registered."""
    registry = PlatformRegistry()
    for adapter_cls in (XAdapter, LinkedInAdapter, GitHubAdapter, EmailAdapter, SlackAdapter):
        registry.register(adapter_cls())
    return registry


def _is_coder_persona(persona: AgentPersona) -> bool:
    """Return True if the persona's tools suggest a CoderAgent."""
    return bool(set(persona.tools) & _CODER_TOOL_NAMES)


class SimulationEngine:
    """Top-level orchestrator that owns every subsystem and drives the simulation.

    Instantiate with a validated :class:`FullConfig`, then call :meth:`start`
    to begin the simulation loop and :meth:`stop` to tear everything down.
    """

    def __init__(self, config: FullConfig) -> None:
        self._config = config

        # Shared subsystems.
        self._event_bus = EventBus()
        self._clock = SimulationClock(
            tick_interval_seconds=config.simulation.tick_interval_seconds,
        )
        self._tool_dispatcher = _build_tool_dispatcher()
        self._platform_registry = _build_platform_registry()

        # Shared mutable world state protected by an asyncio lock.
        self._world_state: dict[str, Any] = {}
        self._world_state_lock = asyncio.Lock()

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
                tool_dispatcher=self._tool_dispatcher,
                tick_interval=0.05,
            )
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
        await self._supervisor.start_all()
        self._clock.start()

        # Launch the background tick loop.
        self._tick_task = asyncio.get_running_loop().create_task(
            self._tick_loop(), name="engine:tick_loop"
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
            if max_ticks is not None and self._clock.elapsed_ticks >= max_ticks:
                log.info("engine.max_ticks_reached", ticks=self._clock.elapsed_ticks)
                break
