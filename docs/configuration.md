# Configuration Reference

entwine is configured via a YAML or TOML file and environment variables. Env vars override config file values, which override defaults.

## Config file format

Supported: `.yaml`, `.yml`, `.toml`. Passed via `--config` flag or `ENTWINE_CONFIG_FILE` env var.

## Simulation section

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | str | *required* | Simulation name (displayed in dashboard) |
| `tick_interval_seconds` | float | `60.0` | Wall-clock seconds between ticks |
| `max_ticks` | int \| null | `null` | Stop after N ticks; null = run indefinitely |
| `log_level` | str | `"INFO"` | Python log level (DEBUG, INFO, WARNING, ERROR) |
| `global_budget_usd` | float \| null | `null` | Max total LLM spend; pauses simulation when reached |
| `per_agent_budget_usd` | float \| null | `null` | Max LLM spend per agent; raises BudgetExceeded |

```yaml
simulation:
  name: "Acme Corp Simulation"
  tick_interval_seconds: 30
  max_ticks: 2880
  log_level: "INFO"
  global_budget_usd: 50.0
  per_agent_budget_usd: 15.0
```

## Enterprise section

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | str | *required* | Company name |
| `description` | str | `""` | Company description (included in agent prompts) |
| `departments` | list | `[]` | Department definitions |
| `departments[].name` | str | *required* | Department name |
| `departments[].description` | str | `""` | Department description |

```yaml
enterprise:
  name: "Acme Corp"
  description: "A fast-growing B2B SaaS company building developer tooling."
  departments:
    - name: "Engineering"
      description: "Product development and infrastructure."
    - name: "Marketing"
      description: "Brand and demand generation."
```

## Agents section

Each agent is a list entry under `agents:`.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | str | *required* | Unique agent name |
| `role` | str | *required* | Job title |
| `department` | str | `""` | Must match a department name |
| `goal` | str | *required* | Primary objective (shapes LLM behaviour) |
| `backstory` | str | `""` | Background context for the persona |
| `llm_tier` | str | `"standard"` | Model tier: `routine`, `standard`, or `complex` |
| `tools` | list[str] | `[]` | Tool names available to this agent |
| `rag_access` | list[str] | `[]` | RAG collection/scope names this agent may query |
| `working_hours.start` | str | `"09:00"` | Format: `HH:MM` |
| `working_hours.end` | str | `"17:00"` | Format: `HH:MM` |

### LLM tiers

| Tier | Default model | Use case |
|------|---------------|----------|
| `routine` | `anthropic/claude-haiku-4-5` | Simple tasks, acknowledgements |
| `standard` | `anthropic/claude-sonnet-4-6` | General reasoning, drafting |
| `complex` | `anthropic/claude-opus-4-6` | Strategic planning, complex decisions |

```yaml
agents:
  - name: "Alice Chen"
    role: "Chief Executive Officer"
    department: "Executive"
    goal: >
      Drive company growth and align departments on strategic priorities.
    backstory: >
      Serial entrepreneur with two successful exits in developer tooling.
    llm_tier: "complex"
    tools: [draft_email, schedule_meeting, read_company_metrics, query_knowledge]
    rag_access: [company-wide, executive, engineering]
    working_hours:
      start: "07:30"
      end: "19:00"
```

## Environment variables

### LLM settings

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | — | Anthropic API key (required) |
| `OPENAI_API_KEY` | — | OpenAI API key (for embeddings + fallback) |
| `ENTWINE_LLM_ROUTINE_MODEL` | `anthropic/claude-haiku-4-5` | Routine tier model |
| `ENTWINE_LLM_STANDARD_MODEL` | `anthropic/claude-sonnet-4-6` | Standard tier model |
| `ENTWINE_LLM_COMPLEX_MODEL` | `anthropic/claude-opus-4-6` | Complex tier model |

### RAG settings

| Variable | Default | Description |
|----------|---------|-------------|
| `RAG_QDRANT_URL` | `http://localhost:6333` | Qdrant server URL |
| `RAG_COLLECTION_NAME` | `enterprise_knowledge` | Qdrant collection name |
| `RAG_EMBEDDING_MODEL` | `text-embedding-3-small` | OpenAI embedding model |
| `RAG_EMBEDDING_DIMENSIONS` | `1536` | Embedding vector dimensions |
| `RAG_ENABLE_HYBRID` | `false` | Enable hybrid search (dense + sparse + RRF) |
| `RAG_RRF_K` | `60` | RRF fusion constant (higher = more weight to lower-ranked results) |

### RAG tuning

**Hybrid search** combines dense vector search (semantic similarity via `text-embedding-3-small`) with sparse vector search (BM25-style term matching) using Reciprocal Rank Fusion (RRF).

**Recommended settings:**

| Setting | Value | Rationale |
|---------|-------|-----------|
| `RAG_ENABLE_HYBRID` | `true` | Hybrid retrieval improves recall for keyword-heavy queries |
| `RAG_RRF_K` | `60` | Standard RRF constant; lower values (e.g. 20) favour top-ranked results more aggressively |
| Chunk size | `500` chars | Balances context completeness with retrieval precision |
| Chunk overlap | `100` chars | Prevents information loss at chunk boundaries |

**Evaluation:** Run `entwine evaluate-rag --dataset examples/evaluation/rag_eval_dataset.json` to compare dense-only vs hybrid retrieval quality (P@5, R@5, MRR) on a 20-query evaluation dataset.

### Platform credentials

See [Platform setup guides](platforms/) for per-platform details.

| Variable | Platform |
|----------|----------|
| `ENTWINE_SLACK_BOT_TOKEN` | Slack |
| `ENTWINE_GITHUB_TOKEN`, `ENTWINE_GITHUB_OWNER`, `ENTWINE_GITHUB_REPO` | GitHub |
| `ENTWINE_EMAIL_CREDENTIALS_JSON`, `ENTWINE_EMAIL_TOKEN_JSON` | Gmail |
| `ENTWINE_X_API_KEY`, `ENTWINE_X_API_SECRET`, `ENTWINE_X_ACCESS_TOKEN`, `ENTWINE_X_ACCESS_TOKEN_SECRET`, `ENTWINE_X_BEARER_TOKEN` | X (Twitter) |

### Application settings

| Variable | Default | Description |
|----------|---------|-------------|
| `ENTWINE_LOG_LEVEL` | `INFO` | Override config file log level |
| `ENTWINE_CONFIG_FILE` | `entwine.yaml` | Default config file path |

## Precedence

Environment variables > config file values > Pydantic defaults.

## Full example

See [`examples/entwine.yaml`](../examples/entwine.yaml) for a complete 4-agent Acme Corp configuration.
