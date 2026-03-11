# Gmail Setup

## Prerequisites

- Google Cloud project
- `google-api-python-client` installed: `uv sync --extra email`

## Steps

### 1. Create a Google Cloud project

1. Go to https://console.cloud.google.com
2. Create a new project (or select existing)
3. Enable the **Gmail API**: APIs & Services > Library > search "Gmail API" > Enable

### 2. Configure OAuth consent screen

1. APIs & Services > OAuth consent screen
2. User type: **Internal** (for workspace) or **External** (for testing)
3. Add scopes: `gmail.send`, `gmail.readonly`
4. Add test users if external

### 3. Create OAuth credentials

1. APIs & Services > Credentials > Create Credentials > OAuth client ID
2. Application type: **Desktop app**
3. Download the JSON file as `credentials.json`

### 4. Set environment variables

```bash
ENTWINE_EMAIL_CREDENTIALS_JSON=credentials.json    # path to OAuth credentials
ENTWINE_EMAIL_TOKEN_JSON=token.json                # path for stored auth token
ENTWINE_EMAIL_USER_EMAIL=agent@company.com         # optional, defaults to "me"
```

### 5. First-run authorization

On first run, a browser window opens for OAuth consent. After authorizing, the token is saved to `token.json` for subsequent runs.

## Verify

```bash
uv run entwine start --config examples/entwine.yaml
# Check logs for: "email: real adapter (EmailLiveAdapter)"
```

## Available actions

| Action | Payload | Description |
|--------|---------|-------------|
| `send_email` | `{to, subject?, body?}` | Send an email |
| `read_inbox` | query string | Search inbox (Gmail search syntax) |

## Notes

- The Google API client is synchronous; entwine wraps calls in `asyncio.run_in_executor` for non-blocking operation
- Token refresh is automatic via `google-auth-oauthlib`

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `google-api-python-client not installed` | Run `uv sync --extra email` |
| OAuth consent screen error | Ensure Gmail API is enabled and test user is added |
| `token.json` invalid | Delete `token.json` and re-authorize |
| `403 insufficient permissions` | Check OAuth scopes include `gmail.send` and `gmail.readonly` |
