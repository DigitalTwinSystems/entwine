"""Shared helpers for scenario tests."""

from __future__ import annotations

from typing import Any

from entwine.agents.models import AgentPersona
from entwine.config.models import EnterpriseConfig, FullConfig, SimulationConfig
from entwine.llm.models import CompletionResponse, LLMTier


def make_persona(name: str, role: str, **overrides: Any) -> AgentPersona:
    defaults: dict[str, Any] = {
        "name": name,
        "role": role,
        "goal": f"Fulfill {role} duties",
        "backstory": f"Experienced {role}",
        "llm_tier": "standard",
        "tools": [],
        "rag_access": [],
    }
    defaults.update(overrides)
    return AgentPersona(**defaults)


def make_config(agents: list[AgentPersona], **sim_overrides: Any) -> FullConfig:
    sim_defaults: dict[str, Any] = {
        "name": "scenario_test",
        "tick_interval_seconds": 0.01,
        "max_ticks": None,
    }
    sim_defaults.update(sim_overrides)
    return FullConfig(
        simulation=SimulationConfig(**sim_defaults),
        enterprise=EnterpriseConfig(name="ScenarioCorp"),
        agents=agents,
    )


class ScriptedLLMRouter:
    """Returns scripted responses keyed by agent name.

    Responses are consumed in order per agent. After exhaustion,
    returns a generic "no more responses" string.
    """

    def __init__(self, scripts: dict[str, list[str]]) -> None:
        self._scripts: dict[str, list[str]] = {k: list(v) for k, v in scripts.items()}
        self.calls: list[dict[str, Any]] = []

    async def complete(
        self,
        tier: LLMTier,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> CompletionResponse:
        # Infer agent name from system prompt or last user message.
        agent_name = _extract_agent_name(messages)
        self.calls.append({"agent": agent_name, "tier": tier.value})

        content = "(no scripted response)"
        if self._scripts.get(agent_name):
            content = self._scripts[agent_name].pop(0)

        return CompletionResponse(
            tier=tier,
            model="scripted",
            content=content,
            input_tokens=50,
            output_tokens=25,
            cost_usd=0.001,
        )


def _extract_agent_name(messages: list[dict[str, Any]]) -> str:
    """Best-effort extraction of agent name from chat messages."""
    for msg in messages:
        if msg.get("role") == "system":
            content = msg.get("content", "")
            # Agent system prompts typically start with "You are {name},"
            if "You are " in content:
                after = content.split("You are ", 1)[1]
                name = after.split(",")[0].split(".")[0].strip()
                return name
    return "unknown"
