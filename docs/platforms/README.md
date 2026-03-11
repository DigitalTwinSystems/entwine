# Platform Adapter Setup Guides

entwine agents interact with real external platforms. Each adapter auto-selects real or stub mode based on available credentials — no code changes needed.

| Platform | Mode | Guide |
|----------|------|-------|
| [Slack](slack.md) | Real (via `slack-sdk`) | Bot token setup |
| [GitHub](github.md) | Real (via `httpx`) | PAT or GitHub App |
| [Gmail](gmail.md) | Real (via Google API) | OAuth consent flow |
| [X / Twitter](x.md) | Real (via `tweepy`) | Developer portal |
| [LinkedIn](linkedin.md) | Simulated only | ADR-006 rationale |

## How adapter selection works

The factory (`entwine.platforms.factory.build_platform_registry`) checks for each platform:

1. Are the required env vars set?
2. Is the SDK installed (for Slack, X, Gmail)?

If both: real adapter. Otherwise: stub adapter with simulated responses. LinkedIn is always simulated per [ADR-006](../adr/006-platform-api-integration.md).

## Installing platform SDKs

```bash
uv sync --extra platforms   # all: slack-sdk, tweepy, google-api-python-client
uv sync --extra slack       # Slack only
uv sync --extra email       # Gmail only
uv sync --extra x           # X/Twitter only
uv sync --extra github      # no extra deps (uses httpx from core)
```
