"""Performance benchmarks for the simulation engine (#44).

Measures tick processing time, event bus throughput, memory usage, and
LLM call latency. CI-runnable; outputs structured JSON results.

Run: uv run python -m pytest tests/benchmarks/ -v -s
"""

from __future__ import annotations

import asyncio
import json
import statistics
import sys
import time
from typing import Any

import pytest

from entwine.agents.models import AgentPersona
from entwine.config.models import EnterpriseConfig, FullConfig, SimulationConfig
from entwine.events.bus import EventBus
from entwine.events.models import SystemEvent
from entwine.llm.models import CompletionResponse, LLMTier
from entwine.simulation.engine import SimulationEngine

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class TimedFakeLLMRouter:
    """Fake router that records call latencies."""

    def __init__(self, latency_ms: float = 1.0) -> None:
        self._latency = latency_ms / 1000.0
        self.latencies: list[float] = []

    async def complete(
        self,
        tier: LLMTier,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> CompletionResponse:
        start = time.perf_counter()
        await asyncio.sleep(self._latency)
        elapsed = time.perf_counter() - start
        self.latencies.append(elapsed * 1000)  # ms
        return CompletionResponse(
            tier=tier,
            model="bench-fake",
            content="benchmark response",
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.001,
        )


def _bench_config(num_agents: int = 4, max_ticks: int = 10) -> FullConfig:
    agents = [
        AgentPersona(
            name=f"bench_agent_{i}",
            role=f"Bench Role {i}",
            goal="Benchmark",
            backstory="Benchmark agent",
            llm_tier="routine",
            tools=[],
            rag_access=[],
        )
        for i in range(num_agents)
    ]
    return FullConfig(
        simulation=SimulationConfig(
            name="benchmark",
            tick_interval_seconds=0.01,
            max_ticks=max_ticks,
        ),
        enterprise=EnterpriseConfig(name="BenchCorp"),
        agents=agents,
    )


def _percentile(data: list[float], pct: float) -> float:
    """Return the p-th percentile of a sorted dataset."""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * (pct / 100)
    f = int(k)
    c = f + 1
    if c >= len(sorted_data):
        return sorted_data[f]
    return sorted_data[f] + (k - f) * (sorted_data[c] - sorted_data[f])


def _print_results(name: str, results: dict[str, Any]) -> None:
    """Print benchmark results as structured JSON."""
    output = {"benchmark": name, **results}
    print(f"\n--- BENCHMARK: {name} ---")
    print(json.dumps(output, indent=2))


# ---------------------------------------------------------------------------
# Event bus throughput
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_event_bus_throughput() -> None:
    """Measure events/sec the bus can dispatch."""
    bus = EventBus()
    await bus.start()

    count = 0

    def counter(event: Any) -> None:
        nonlocal count
        count += 1

    bus.subscribe_all(counter)

    num_events = 1000
    start = time.perf_counter()

    for i in range(num_events):
        await bus.publish(SystemEvent(source_agent="bench", payload={"i": i}))

    # Wait for all events to be dispatched.
    await asyncio.sleep(0.5)
    elapsed = time.perf_counter() - start

    await bus.stop()

    throughput = count / elapsed
    _print_results(
        "event_bus_throughput",
        {
            "events_published": num_events,
            "events_received": count,
            "elapsed_seconds": round(elapsed, 3),
            "throughput_events_per_sec": round(throughput, 1),
        },
    )

    # Sanity: should handle at least 500 events/sec.
    assert throughput > 500


# ---------------------------------------------------------------------------
# Tick processing time
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tick_processing_time() -> None:
    """Measure per-tick processing latency with N agents."""
    num_agents = 4
    num_ticks = 10
    config = _bench_config(num_agents=num_agents, max_ticks=num_ticks)
    router = TimedFakeLLMRouter(latency_ms=1.0)
    engine = SimulationEngine(config, llm_router=router)  # type: ignore[arg-type]

    start = time.perf_counter()
    await engine.start()

    # Wait for ticks to complete.
    await asyncio.sleep(1.0)
    await engine.stop()
    elapsed = time.perf_counter() - start

    avg_tick_ms = (elapsed / max(engine.elapsed_ticks, 1)) * 1000

    _print_results(
        "tick_processing_time",
        {
            "num_agents": num_agents,
            "ticks_completed": engine.elapsed_ticks,
            "total_seconds": round(elapsed, 3),
            "avg_tick_ms": round(avg_tick_ms, 2),
            "llm_calls": len(router.latencies),
        },
    )

    # Sanity: ticks should complete (even with fake LLM latency).
    assert engine.elapsed_ticks >= 1


# ---------------------------------------------------------------------------
# LLM call latency percentiles
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_llm_call_latency_percentiles() -> None:
    """Measure p50/p95/p99 of LLM call latencies."""
    config = _bench_config(num_agents=2, max_ticks=5)
    router = TimedFakeLLMRouter(latency_ms=2.0)
    engine = SimulationEngine(config, llm_router=router)  # type: ignore[arg-type]

    await engine.start()
    await asyncio.sleep(0.5)
    await engine.stop()

    latencies = router.latencies
    if latencies:
        _print_results(
            "llm_call_latency",
            {
                "num_calls": len(latencies),
                "p50_ms": round(_percentile(latencies, 50), 2),
                "p95_ms": round(_percentile(latencies, 95), 2),
                "p99_ms": round(_percentile(latencies, 99), 2),
                "mean_ms": round(statistics.mean(latencies), 2),
                "max_ms": round(max(latencies), 2),
            },
        )

    assert len(latencies) >= 1


# ---------------------------------------------------------------------------
# Memory usage under load
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_memory_usage_under_load() -> None:
    """Track RSS memory growth with N agents over M ticks."""
    import resource

    num_agents = 8
    num_ticks = 20
    config = _bench_config(num_agents=num_agents, max_ticks=num_ticks)
    router = TimedFakeLLMRouter(latency_ms=0.5)

    mem_before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss

    engine = SimulationEngine(config, llm_router=router)  # type: ignore[arg-type]
    await engine.start()
    await asyncio.sleep(1.5)
    await engine.stop()

    mem_after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # macOS reports in bytes, Linux in KB.
    mem_delta_kb = (mem_after - mem_before) / (1 if sys.platform == "linux" else 1024)

    _print_results(
        "memory_usage",
        {
            "num_agents": num_agents,
            "num_ticks": num_ticks,
            "mem_before_kb": round(mem_before / (1 if sys.platform == "linux" else 1024)),
            "mem_after_kb": round(mem_after / (1 if sys.platform == "linux" else 1024)),
            "mem_delta_kb": round(mem_delta_kb),
            "llm_calls": len(router.latencies),
        },
    )

    # Memory growth should be bounded (no major leaks).
    # Allow generous limit for CI variability.
    assert mem_delta_kb < 100_000  # < 100 MB growth
