"""Supervisor: manages a pool of BaseAgent instances and watches for failures."""

from __future__ import annotations

import asyncio
import contextlib
from typing import Literal

import structlog

from entsim.agents.base import BaseAgent
from entsim.agents.models import AgentState

log = structlog.get_logger(__name__)

RecoveryStrategy = Literal["restart", "pause", "skip"]


class Supervisor:
    """Plain-Python asyncio supervisor for a fixed set of BaseAgent instances.

    Responsibilities
    ----------------
    - Starts / stops all registered agents.
    - Exposes per-agent pause and resume.
    - Monitors each agent's asyncio Task for unhandled exceptions.
    - On failure, applies the configured RecoveryStrategy:
        ``restart`` — reinitialise and restart the agent.
        ``pause``   — leave agent in ERROR state and log an alert.
        ``skip``    — mark agent as degraded; simulation continues without it.
    """

    def __init__(
        self,
        agents: list[BaseAgent] | None = None,
        *,
        default_recovery: RecoveryStrategy = "skip",
    ) -> None:
        self._agents: dict[str, BaseAgent] = {}
        self._recovery: dict[str, RecoveryStrategy] = {}
        self._default_recovery = default_recovery
        self._watch_task: asyncio.Task[None] | None = None

        for agent in agents or []:
            self.register(agent)

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        agent: BaseAgent,
        recovery: RecoveryStrategy | None = None,
    ) -> None:
        """Register an agent with the supervisor.

        Parameters
        ----------
        agent:
            A BaseAgent instance in READY (or CREATED) state.
        recovery:
            Override the default recovery strategy for this agent.
        """
        if agent.name in self._agents:
            raise ValueError(f"Agent '{agent.name}' is already registered.")
        self._agents[agent.name] = agent
        self._recovery[agent.name] = recovery or self._default_recovery
        log.info("supervisor.agent_registered", agent=agent.name)

    # ------------------------------------------------------------------
    # Bulk lifecycle
    # ------------------------------------------------------------------

    async def start_all(self) -> None:
        """Start every registered agent and launch the watcher task."""
        for agent in self._agents.values():
            if agent.state == AgentState.READY:
                agent.start()
            else:
                log.warning(
                    "supervisor.start_skipped",
                    agent=agent.name,
                    state=agent.state.value,
                )
        self._watch_task = asyncio.get_running_loop().create_task(
            self._watch_agents(), name="supervisor:watcher"
        )
        log.info("supervisor.all_started", count=len(self._agents))

    async def stop_all(self) -> None:
        """Stop every registered agent and cancel the watcher task."""
        if self._watch_task is not None and not self._watch_task.done():
            self._watch_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._watch_task
            self._watch_task = None

        stop_coros = [agent.stop() for agent in self._agents.values()]
        await asyncio.gather(*stop_coros, return_exceptions=True)
        log.info("supervisor.all_stopped")

    # ------------------------------------------------------------------
    # Per-agent control
    # ------------------------------------------------------------------

    async def pause_agent(self, name: str) -> None:
        """Pause a named agent.

        Raises KeyError if the agent is not registered.
        """
        agent = self._get(name)
        await agent.pause()

    async def resume_agent(self, name: str) -> None:
        """Resume a named paused agent.

        Raises KeyError if the agent is not registered.
        """
        agent = self._get(name)
        await agent.resume()

    # ------------------------------------------------------------------
    # Watcher
    # ------------------------------------------------------------------

    async def _watch_agents(self) -> None:
        """Continuously poll agent tasks for completion / exceptions."""
        while True:
            await asyncio.sleep(0.1)
            for name, agent in list(self._agents.items()):
                if not agent.is_task_done:
                    continue
                if agent.is_task_cancelled:
                    log.info("supervisor.task_cancelled", agent=name)
                    continue
                exc = agent.task_exception
                if exc is None:
                    continue
                log.error(
                    "supervisor.agent_exception",
                    agent=name,
                    error=str(exc),
                    exc_info=exc,
                )
                await self._recover(name, agent)

    async def _recover(self, name: str, agent: BaseAgent) -> None:
        """Apply the configured recovery strategy for a failed agent."""
        strategy = self._recovery.get(name, self._default_recovery)
        log.warning(
            "supervisor.recovering",
            agent=name,
            strategy=strategy,
            current_state=agent.state.value,
        )

        if strategy == "restart":
            # Re-use the existing persona and concrete class; build a fresh agent.
            agent_cls = type(agent)
            new_agent = agent_cls(persona=agent.persona, event_bus=agent.event_bus)
            new_agent.start()
            self._agents[name] = new_agent
            log.info("supervisor.agent_restarted", agent=name)

        elif strategy == "pause":
            # Leave agent in ERROR state; alert operator via log.
            log.critical(
                "supervisor.agent_degraded_manual_intervention_required",
                agent=name,
            )

        else:  # "skip"
            log.warning("supervisor.agent_skipped", agent=name)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get(self, name: str) -> BaseAgent:
        try:
            return self._agents[name]
        except KeyError as err:
            raise KeyError(f"No agent named '{name}' is registered with this supervisor.") from err
