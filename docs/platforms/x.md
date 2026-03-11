# X (Twitter) Setup

## Prerequisites

- X Developer account with Basic tier ($200/month)
- `tweepy` installed: `uv sync --extra x`

## Steps

### 1. Create a Developer App

1. Go to https://developer.x.com/en/portal/dashboard
2. Create a new project and app
3. Set up **User authentication** with OAuth 1.0a (read and write)

### 2. Generate keys

In your app settings, generate:
- API Key and Secret (consumer credentials)
- Access Token and Secret (user credentials)
- Bearer Token (for search endpoints)

### 3. Set environment variables

```bash
ENTWINE_X_API_KEY=...
ENTWINE_X_API_SECRET=...
ENTWINE_X_ACCESS_TOKEN=...
ENTWINE_X_ACCESS_TOKEN_SECRET=...
ENTWINE_X_BEARER_TOKEN=...
```

All five are required for the real adapter.

## Verify

```bash
uv run entwine start --config examples/entwine.yaml
# Check logs for: "x: real adapter (XLiveAdapter)"
```

## Available actions

| Action | Payload | Description |
|--------|---------|-------------|
| `post_tweet` | `{text, reply_to?}` | Post a tweet (optionally as reply) |
| `read_timeline` | query string | Search recent tweets |

## Rate limits

X Basic tier rate limits apply. The adapter uses `tweepy.AsyncClient` which handles rate limit headers automatically.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `tweepy not installed` | Run `uv sync --extra x` |
| `401 Unauthorized` | Regenerate keys in developer portal |
| `403 Forbidden` | Ensure Basic tier subscription is active |
| Tweet not posting | Check app has read+write permissions |
