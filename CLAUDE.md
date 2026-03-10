# entsim — Claude Code Instructions

## Documentation standards

- All documentation must be succinct. Prefer tables and bullet points over prose.
- Reference external information with permalinks (pinned to commit, version, or archive), not mutable URLs.
- ADRs go in `docs/adr/` and follow the format established in `docs/adr/001-programming-language-and-runtime.md`.

## Project conventions

- Language: Python 3.12+ (see ADR-001)
- Package manager: uv
- Linting/formatting: ruff
- Async runtime: asyncio (stdlib)
- LLM integration: LiteLLM Router with Anthropic primary, OpenAI fallback (see ADR-002)
