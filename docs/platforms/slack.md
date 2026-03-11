# Slack Setup

## Prerequisites

- Slack workspace with admin access
- `slack-sdk` installed: `uv sync --extra slack`

## Steps

### 1. Create a Slack App

1. Go to https://api.slack.com/apps
2. Click **Create New App** > **From scratch**
3. Name: `entwine`, select your workspace

### 2. Configure bot permissions

Navigate to **OAuth & Permissions** > **Bot Token Scopes**, add:

| Scope | Purpose |
|-------|---------|
| `chat:write` | Send messages |
| `channels:read` | List channels |
| `channels:history` | Read channel messages |
| `reactions:write` | Add emoji reactions |

### 3. Install to workspace

Click **Install to Workspace**, authorize. Copy the **Bot User OAuth Token** (`xoxb-...`).

### 4. Set environment variables

```bash
ENTWINE_SLACK_BOT_TOKEN=xoxb-your-token-here
ENTWINE_SLACK_DEFAULT_CHANNEL=#general    # optional, defaults to #general
```

### 5. Invite bot to channels

In Slack, invite the bot to channels agents will use:
```
/invite @entwine
```

## Verify

```bash
uv run entwine start --config examples/entwine.yaml
# Check logs for: "slack: real adapter (SlackLiveAdapter)"
```

## Available actions

| Action | Payload | Description |
|--------|---------|-------------|
| `send_message` | `{channel, text}` | Post to a channel |
| `add_reaction` | `{channel, timestamp, emoji}` | React to a message |
| `read_channel` | query string | Read messages from default channel |

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `slack_sdk not installed` in logs | Run `uv sync --extra slack` |
| `invalid_auth` error | Regenerate bot token, update env var |
| Bot can't post to channel | Invite bot with `/invite @entwine` |
