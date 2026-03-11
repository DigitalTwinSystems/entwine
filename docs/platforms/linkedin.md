# LinkedIn (Simulated)

## Status

LinkedIn is **always simulated**. Per [ADR-006](../adr/006-platform-api-integration.md), the LinkedIn Marketing API requires partner-level approval that is not available for simulation use cases.

## What the simulator does

`LinkedInSimAdapter` records all intended actions in an internal log and returns plausible synthetic responses with fake engagement metrics (impressions, likes, comments).

## Available actions

| Action | Payload | Description |
|--------|---------|-------------|
| `post_update` | any | Log a post; returns synthetic engagement |
| `read_feed` | query string | Returns simulated feed items |
| `send_message` | any | Log a DM; returns confirmation |

## Observability

Access the action log programmatically:

```python
adapter = platform_registry.get("linkedin")
for entry in adapter.action_log:
    print(entry)  # {"action": "post_update", "payload": {...}, "response": {...}}
```

## Promoting to real

If LinkedIn partner API access is obtained, implement `LinkedInLiveAdapter` following the same `PlatformAdapter` interface. Update the factory to select it when credentials are present. No agent code changes needed.
