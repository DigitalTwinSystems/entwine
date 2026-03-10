# ADR-006: Platform API Integration Feasibility

**Status:** Accepted
**Date:** 2026-03-10
**Issue:** [#6](https://github.com/DigitalTwinSystems/entwine/issues/6)

## Context

entwine agents must interact with external platforms to simulate realistic SME operations. This ADR evaluates which platforms expose usable APIs for automated agents, what authentication is required, what the cost and rate-limit constraints are, and whether real or simulated integrations are appropriate.

Constraints from prior ADRs:

- Python 3.12 + asyncio (ADR-001)
- Agents call LLMs via LiteLLM Router (ADR-002)
- Shared Qdrant knowledge base (ADR-003)
- Config-as-code, HTMX monitoring UI (ADR-004)

## Platform Feasibility Matrix

| Platform | Auth Method | Can Post? | Can Read? | Rate Limit | Monthly Cost | App Review? | Verdict |
|---|---|---|---|---|---|---|---|
| **X (Twitter)** | OAuth 2.0 / Bearer token | Yes | Yes (paid) | 15K reads/mo (Basic) | $200 (Basic) / $5K (Pro) | No (self-serve) | Real – Basic tier |
| **LinkedIn** | OAuth 2.0 (3-legged) | Yes (org posts) | Limited | 100K calls/day | Partner program (free/gated) | Yes – Partner approval | Simulate unless partner-approved |
| **Gmail** | OAuth 2.0 (3-legged) | Yes | Yes | 15K quota units/user/min | Free (Workspace billed separately) | Light (Google verification) | Real |
| **Office 365** | OAuth 2.0 (client creds or delegated) | Yes | Yes | 10K req/10 min/mailbox | Free API (M365 license required) | No (Azure app reg) | Real |
| **Reddit** | OAuth 2.0 | Yes | Yes | 60 req/min (standard) | Free / $0.24 per 1K calls (commercial) | No (self-serve; elevated needs approval) | Real – standard tier |
| **Slack** | OAuth 2.0 / Bot token | Yes | Limited (internal apps) | 1 req/sec general; 1 req/min for history (non-Marketplace) | Free API (Slack workspace plan billed) | Marketplace review for high limits | Real – internal app |
| **GitHub** | OAuth 2.0 / PAT / GitHub App | Yes | Yes | 5K req/hr (authenticated) | Free | No (self-serve) | Real |

## Per-Platform Detail

### X (Twitter)

- **Tiers:** Free (write-only, 1.5K posts/mo, no reads), Basic ($200/mo, 15K reads + 50K posts), Pro ($5K/mo, 1M reads). Pay-as-you-go launched February 2026. ([getlate.dev](https://getlate.dev/blog/twitter-api-pricing), [docs.x.com rate limits](https://docs.x.com/x-api/fundamentals/rate-limits))
- **Auth:** OAuth 2.0 (user context) for posting; Bearer token (app-only) for read. No app-review gatekeeping — self-serve sign-up.
- **Decision:** Use **Basic tier** ($200/mo). Sufficient for a simulation with ~12 agents posting and reading at SME-realistic volumes. If read volume exceeds 15K/mo, consider pay-as-you-go.

### LinkedIn

- **Access model:** Restricted to LinkedIn Partner Program members. Org posts via Community Management API (3-legged OAuth, `w_member_social` / `r_organization_social` scopes). Daily cap: 100K API calls. Profile data storage limited to 24 h. ([learn.microsoft.com Posts API](https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/posts-api?view=li-lms-2026-01), [learn.microsoft.com restricted uses](https://learn.microsoft.com/en-us/linkedin/marketing/restricted-use-cases?view=li-lms-2026-01))
- **Prohibited:** Automated lead generation, member data for advertising, scraping.
- **App review:** Must apply to and be accepted into a LinkedIn Partner product category (Talent, Marketing, Sales Navigator, or Learning Solutions). No self-serve general API.
- **Decision:** **Simulate** LinkedIn interactions for now. Build a `LinkedInAdapter` stub that logs intended actions and records them in Qdrant. Re-evaluate if a partner relationship is established.

### Gmail

- **Auth:** OAuth 2.0 with 3-legged flow per user. Refresh tokens are long-lived. Sensitive scopes (`gmail.send`, `gmail.readonly`) require Google's OAuth verification if the app will be used by non-test users. ([developers.google.com quota](https://developers.google.com/workspace/gmail/api/reference/quota))
- **Rate limits:** 1.2M quota units/min per project; 15K quota units/user/min. Sending a message = 100 units, so each user can send ~150 emails/min before hitting the per-user cap. Workspace sending limits (not API limits) cap at 2K messages/day per account.
- **Cost:** API is free; underlying Google Workspace license is $6–$18/user/month depending on plan.
- **Decision:** **Real integration**. Use `google-auth-oauthlib` + `googleapiclient`. Store refresh tokens encrypted in config (ADR-004 config-as-code). Implement exponential backoff on 429/403 responses.

### Office 365 / Microsoft Graph

- **Auth:** OAuth 2.0 via Azure AD — either delegated (user-interactive, 3-legged) or client credentials (app-only, for shared mailboxes / service accounts). Register app in Azure Portal; no formal review required. ([learn.microsoft.com throttling](https://learn.microsoft.com/en-us/graph/throttling-limits))
- **Rate limits:** Outlook service — 10K requests per 10 minutes per app+mailbox combination (~16 req/sec). Cannot be raised; bulk use cases should use Microsoft Graph Data Connect.
- **Scopes needed:** `Mail.ReadWrite`, `Mail.Send`, `Calendars.ReadWrite`.
- **Cost:** Graph API is free; Microsoft 365 Business Basic is $6/user/month.
- **Decision:** **Real integration**. Use `msal` (Microsoft Authentication Library for Python) with client-credentials flow for service accounts. Store client secret in environment config.

### Reddit

- **Auth:** OAuth 2.0 (script app type for server-side automation). Register app at reddit.com/prefs/apps — no review needed for standard access. ([painonsocial.com rate limits guide](https://painonsocial.com/blog/reddit-api-rate-limits-guide))
- **Rate limits:** 60 req/min (OAuth), 10 req/min (unauthenticated). Elevated access (600–1K req/min) requires manual Reddit approval.
- **Cost:** Free for non-commercial / personal. Commercial use billed at $0.24 per 1K API calls. For a simulation with ~12 agents at realistic SME volumes, cost stays negligible.
- **Bot rules:** Automated posting is permitted by Reddit's API ToS provided the bot discloses its nature in its User-Agent and follows subreddit rules. Moderation bots remain free.
- **Decision:** **Real integration** using [`asyncpraw`](https://asyncpraw.readthedocs.io/) (async Python Reddit wrapper). Standard OAuth app, no review needed.

### Slack

- **Auth:** OAuth 2.0 bot token. Create a Slack App in the developer portal; install to a workspace. No Marketplace review required for internal/custom apps. ([docs.slack.dev rate limits](https://docs.slack.dev/apis/web-api/rate-limits/))
- **Rate limits:**
  - General Web API methods: ~1 req/sec burst; Tier 1–4 per-method limits apply.
  - `conversations.history` / `conversations.replies`: 1 req/min + max 15 objects/request for non-Marketplace apps created after May 2025. Internal/custom apps retain 50+ req/min with 1,000 object max. ([docs.slack.dev changelog](https://docs.slack.dev/changelog/2025/05/29/rate-limit-changes-for-non-marketplace-apps/))
- **Cost:** Free API. Workspace plan costs $8.75–$15/user/month; agents connect to a workspace the team already runs.
- **Decision:** **Real integration** using [`slack-sdk`](https://github.com/slackapi/python-slack-sdk) (official Python async client). Register as an **internal app** to retain high rate limits without Marketplace review. Agents post and read within a dedicated simulation workspace.

### GitHub

- **Auth:** Personal Access Token (PAT) for simple automation; GitHub App (installation access token) for multi-repo or org-level automation. Both use OAuth 2.0 under the hood. Self-serve — no review required. ([docs.github.com REST rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api))
- **Rate limits:** 5K req/hr (authenticated user/OAuth app); up to 12.5K/hr for GitHub Apps on large installations. Secondary limits: 100 concurrent requests, 900 REST points/min, 80 content-creating requests/min.
- **Cost:** Free for public and private repos. GitHub Teams ($4/user/month) or Enterprise if needed.
- **Decision:** **Real integration** using [`PyGithub`](https://github.com/PyGithub/PyGithub) or [`httpx`](https://www.python-httpx.org/) directly. Use a GitHub App for agent-level identity (each agent can act under its own installation token).

## Authentication Strategy

All real integrations use OAuth 2.0. Two patterns apply:

| Pattern | Platforms | Notes |
|---|---|---|
| **3-legged (user-delegated)** | X, Gmail, Reddit, Slack | User (or simulated persona) authorizes the app; refresh token stored in encrypted config. |
| **2-legged (service account / client credentials)** | Office 365, GitHub App | No human in the loop; credentials stored as environment secrets. |

Token refresh and retry logic are shared concerns — implement a single `PlatformClient` base class with asyncio-native exponential backoff, respecting `Retry-After` / `X-RateLimit-Reset` headers.

## Simulation Strategy for Restricted Platforms

LinkedIn interactions are simulated via a `LinkedInAdapter` that:

1. Receives the agent's intended action (post text, target audience).
2. Logs the action to the Qdrant event store with status `simulated`.
3. Returns a plausible synthetic response (view count, reaction count drawn from a configurable distribution).
4. Exposes the same interface as real platform adapters so agents are unaware of the difference.

This keeps agent logic platform-agnostic and allows a real LinkedIn integration to be swapped in later without agent code changes.

## Decision

| Platform | Integration Type | Python Library |
|---|---|---|
| X (Twitter) | Real (Basic tier) | [`tweepy`](https://github.com/tweepy/tweepy) (async) |
| LinkedIn | Simulated | Internal `LinkedInAdapter` stub |
| Gmail | Real | `google-auth-oauthlib` + `googleapiclient` |
| Office 365 | Real | `msal` + `httpx` (Graph API) |
| Reddit | Real | `asyncpraw` |
| Slack | Real (internal app) | `slack-sdk` |
| GitHub | Real (GitHub App) | `PyGithub` / `httpx` |

All adapters implement a common async interface (`send`, `read`, `search`) so agents interact with an abstraction layer, not platform SDKs directly.

## Consequences

### Positive

- Six of seven platforms have real, low-friction API access.
- Shared `PlatformClient` base class centralises retry/rate-limit logic and keeps agent code clean.
- Simulated LinkedIn adapter is indistinguishable to agents — easy to promote to real when partner access is obtained.
- All integrations use standard OAuth 2.0; no bespoke auth per platform.

### Negative

- X Basic tier at $200/month is the only ongoing per-platform API cost; must be budgeted.
- LinkedIn simulation means agents cannot receive real LinkedIn signals (notifications, profile views). Simulation fidelity depends on the synthetic response distributions chosen.
- Google and Slack OAuth verification/review may delay initial deployment if moving beyond test users.
- Rate limits across seven platforms require careful per-adapter throttling; a shared rate-limit registry (e.g. in-process `asyncio` token bucket) is needed to avoid cascading 429 errors.

### Out of Scope

- WhatsApp Business API, Telegram, Discord — not listed in issue #6; can be added as future adapters.
- Microsoft Teams — structurally similar to Slack; defer until there is a concrete use case.
