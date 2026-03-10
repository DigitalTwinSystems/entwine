# ADR-002: LLM Providers and Integration Strategy

**Status:** Accepted
**Date:** 2026-03-10
**Issue:** [#2](https://github.com/DigitalTwinSystems/entwine/issues/2)

## Context

entwine runs ~12 concurrent LLM agents simulating SME operations. We need to select LLM providers, define an integration architecture, and establish a cost-effective model tiering strategy.

The workload characteristics: I/O-bound (LLM API latency dominates), moderate concurrency (12 agents), mixed complexity (routine tasks + complex reasoning), and shared context across agents (org structure, simulation rules).

## Decision

### Primary provider: Anthropic (Claude 4.x family)

Use Claude models as the default, with OpenAI as secondary/fallback.

| Role | Model | Cost (in/out per MTok) |
|------|-------|----------------------|
| Routine tasks (classification, extraction, templates) | Claude Haiku 4.5 | $1 / $5 |
| Standard agent reasoning | Claude Sonnet 4.6 | $3 / $15 |
| Complex orchestration, planning | Claude Opus 4.6 | $5 / $25 |

### Integration layer: LiteLLM Router

Use [LiteLLM](https://github.com/BerriAI/litellm) as the provider abstraction layer, with direct SDK access for provider-specific features when needed.

```python
import litellm
from litellm import Router

router = Router(model_list=[
    {"model_name": "routine", "litellm_params": {"model": "anthropic/claude-haiku-4-5"}},
    {"model_name": "standard", "litellm_params": {"model": "anthropic/claude-sonnet-4-6"}},
    {"model_name": "complex", "litellm_params": {"model": "anthropic/claude-opus-4-6"}},
    # Fallbacks
    {"model_name": "standard", "litellm_params": {"model": "openai/gpt-4.1"}},
])
response = await router.acompletion(model="standard", messages=[...])
```

### Model tiering: three tiers mapped to agent roles

- **Tier 1 (routine):** Worker agents doing data retrieval, simple reporting, template filling. Use Haiku 4.5.
- **Tier 2 (standard):** Most agent reasoning — planning steps, knowledge synthesis, platform interactions. Use Sonnet 4.6 (primary) or GPT-4.1 (fallback).
- **Tier 3 (complex):** Orchestration decisions, cross-domain reasoning, high-stakes outputs. Use Opus 4.6.

Target assignment: ~70% Tier 1, ~25% Tier 2, ~5% Tier 3 by request volume.

### Local development: Ollama with open-source models

Use [Ollama](https://ollama.com/) exposing an OpenAI-compatible API for zero-cost local development. Recommended models: Llama 4 Scout, Qwen 3. LiteLLM routes to Ollama via `openai/` prefix with custom `base_url`.

## Rationale

### Why Anthropic as primary

- Best prompt caching economics: cache reads cost 10% of input price and [don't count toward ITPM rate limits on Claude 4.x](https://docs.anthropic.com/en/docs/about-claude/models/all-models#prompt-caching). This is critical for agents sharing context (simulation rules, org charts).
- Claude Sonnet 4.6 offers the best quality/cost ratio at the standard tier for agentic workloads.
- Excellent async Python SDK (`AsyncAnthropic`) with `tool_runner` for automatic tool-call loops.
- At [Tier 3](https://docs.anthropic.com/en/api/rate-limits) (unlocked at ~$200 cumulative spend): 2,000 RPM and 800K ITPM across Sonnet 4.x — comfortable headroom for 12 agents.

### Why LiteLLM over direct SDKs only

- Unified `acompletion()` async interface across providers — one calling convention regardless of backend.
- Built-in [Router](https://docs.litellm.ai/docs/routing) with fallback chains, load balancing strategies, and per-deployment concurrency limits.
- Cost tracking via `litellm.completion_cost()`.
- Directly [integrates with OpenAI Agents SDK](https://openai.github.io/openai-agents-python/models/litellm/) if we adopt it later.
- Trade-off: may lag behind provider-specific features. Mitigated by allowing direct SDK calls where needed.

### Why not OpenAI as primary

GPT-4.1 is competitive ($2/$8, 1M context, strong tool calling), but:
- No equivalent to Anthropic's prompt caching ITPM exemption — a significant throughput multiplier for shared-context agent systems.
- GPT-5.4 ($2.50/$15) is newer but more expensive at the standard tier than Sonnet 4.6.
- OpenAI remains valuable as a fallback provider and for specific models (o4-mini for cheap reasoning).

### Why not Google Gemini as primary

Gemini 2.5 Flash ($0.30/$2.50) is the cheapest capable model available, but:
- Lower rate limits at paid Tier 1 (150–300 RPM vs. Anthropic's 2,000 RPM at Tier 3).
- Python SDK (`google-genai`) is newer and less battle-tested for production agent workloads.
- Viable as a future Tier 1 option if cost pressure increases.

### Cost projection

Estimated cost for 12 agents with tiered model strategy and prompt caching:

| Scenario | Hourly cost |
|----------|------------|
| All Sonnet 4.6, no caching | ~$43/hr |
| All Sonnet 4.6, 60% cache hit | ~$25/hr |
| Tiered (70/25/5), 60% cache hit | ~$8–12/hr |

The tiered strategy reduces cost by ~4x compared to uniform Sonnet usage.

### Rate limit strategy

- Use LiteLLM Router's `max_parallel_requests` per deployment to prevent burst errors.
- Monitor Anthropic's `anthropic-ratelimit-*` response headers for proactive backpressure.
- Leverage prompt caching to reduce effective ITPM consumption.
- Target Anthropic Tier 3 (2,000 RPM, 800K ITPM for Sonnet) — sufficient for 12 agents at ~166 RPM each.
- Cross-provider fallback via LiteLLM if a provider's limits are hit.

## Consequences

### Positive

- Prompt caching + tiering yields ~4x cost reduction vs. naive single-model approach
- LiteLLM provides provider portability — switching or adding providers requires config changes, not code changes
- Fallback chains improve reliability (Anthropic outage → automatic OpenAI fallback)
- Local development with Ollama eliminates API costs during prototyping

### Negative

- LiteLLM adds a dependency that may lag behind provider SDK features
- Tiering logic adds complexity — each agent task must be classified by tier
- Anthropic as primary creates some vendor dependency (mitigated by LiteLLM abstraction and OpenAI fallback)
- Prompt caching requires careful cache key management to maintain high hit rates
