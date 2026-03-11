# GitHub Setup

## Prerequisites

- GitHub account with repo access
- No extra SDK needed (uses `httpx` from core dependencies)

## Steps

### 1. Create a Personal Access Token (PAT)

1. Go to https://github.com/settings/tokens
2. Click **Generate new token (classic)**
3. Select scopes:

| Scope | Purpose |
|-------|---------|
| `repo` | Full repository access (issues, PRs, code) |

4. Copy the token (`ghp_...`)

### 2. Set environment variables

```bash
ENTWINE_GITHUB_TOKEN=ghp_your-token-here
ENTWINE_GITHUB_OWNER=your-org        # repo owner or org name
ENTWINE_GITHUB_REPO=your-repo        # target repository name
```

All three are required for the real adapter.

## Verify

```bash
uv run entwine start --config examples/entwine.yaml
# Check logs for: "github: real adapter (GitHubLiveAdapter)"
```

## Available actions

| Action | Payload | Description |
|--------|---------|-------------|
| `create_issue` | `{title, body?}` | Open a new issue |
| `create_pr` | `{title, head, base?, body?}` | Create a pull request |
| `add_comment` | `{issue_number, body}` | Comment on an issue/PR |
| `list_prs` | `{state?, limit?}` | List pull requests |

Owner and repo default to the configured values but can be overridden per-call.

## Rate limiting

The adapter enforces 80 requests per 60 seconds (within GitHub's 5,000/hour REST limit).

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `401 Unauthorized` | Token expired or invalid; regenerate |
| `404 Not Found` | Check `ENTWINE_GITHUB_OWNER` and `ENTWINE_GITHUB_REPO` |
| Rate limit hit | Adapter retries with exponential backoff automatically |
