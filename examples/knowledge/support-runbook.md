---
department: support
accessible_roles: customer support engineer, cto, developer, devops
sensitivity: internal
---

# Acme Corp Customer Support Runbook

## Ticket Triage

| Priority | Response SLA | Resolution SLA | Examples |
|----------|-------------|----------------|----------|
| P0 — Critical | 15 min | 4 hours | Service outage, data loss, security breach |
| P1 — High | 1 hour | 8 hours | Feature broken, workaround available |
| P2 — Medium | 4 hours | 48 hours | Non-blocking bug, UI glitch, performance degradation |
| P3 — Low | 24 hours | 5 business days | Feature request, docs clarification, billing question |

All tickets are created in Zendesk. Auto-assignment routes tickets based on customer tier (Enterprise customers get priority routing) and topic tags. SLA timers start when the ticket is created, not when it is first viewed.

## Common Issues and Resolution

### Authentication Failures (P1)

**Symptoms**: User cannot log in, SSO redirect loop, "Invalid token" error.

**Steps**:
1. Check if the issue is user-specific or platform-wide (Grafana dashboard: auth-errors panel).
2. If platform-wide: escalate to on-call engineer immediately via PagerDuty.
3. If user-specific: verify SSO config in admin panel, check token expiry, clear session cache.
4. If persistent: regenerate API key and notify the user with new credentials.
5. Document the root cause in the ticket for future reference.

### Slow Search Performance (P2)

**Symptoms**: Search queries taking longer than 2 seconds, timeout errors on large workspaces.

**Steps**:
1. Check Qdrant health: `curl http://qdrant:6333/readyz` (should return 200).
2. Check index status: `curl http://qdrant:6333/collections/enterprise_knowledge` (verify vector count and index status).
3. If collection is large (over 1M vectors): check if HNSW index is rebuilding (can take 5 to 10 minutes after large ingestion).
4. Check if the customer's workspace has unusual content patterns (very long documents, non-text content).
5. If persistent: file GitHub issue with query examples, response times, and collection stats.

### Webhook Delivery Failures (P2)

**Symptoms**: Customer reports missing webhook events, retry queue growing.

**Steps**:
1. Check webhook delivery logs in admin panel (Settings, Webhooks, Delivery History).
2. Verify customer endpoint is reachable: `curl -I <endpoint_url>`.
3. If 4xx response: customer configuration issue — share error details and suggest fixes.
4. If 5xx or timeout: retry manually via admin panel. If persistent, check for rate-limiting on customer side.
5. If delivery queue exceeds 1000 pending events: alert engineering on-call.

### Data Export Requests (P3)

**Symptoms**: Customer requests full data export for compliance or migration.

**Steps**:
1. Verify the requester is an admin-level user on the account.
2. Trigger export via admin panel (Settings, Data, Export). Format: JSON or CSV.
3. Export is processed async. Notify customer when download link is ready (valid for 72 hours).
4. For accounts with more than 100GB of data, coordinate with engineering for a direct database export.

## Escalation Path

1. **L1 Support** (Tariq Hassan): Initial triage, known-issue resolution, password resets, billing questions.
2. **L2 Support** (Senior support engineers): Complex technical issues, multi-step debugging, config review.
3. **Engineering On-Call**: P0 and P1 escalation, unknown bugs, infrastructure issues. Reached via PagerDuty.
4. **CTO** (David Park): Architecture-level issues, customer-impacting outages lasting more than 1 hour.
5. **CEO** (Alice Chen): Customer relationship issues, SLA breach communication, account retention.

## Customer Communication Templates

- **Acknowledgment**: "Thank you for reaching out. We have received your report and are investigating. Our team will provide an update within [SLA time]."
- **Status Update**: "We are actively working on this issue. Current status: [investigating/identified/fix in progress]. Expected resolution: [time estimate]."
- **Resolution**: "The issue has been resolved. Root cause: [brief explanation]. We have taken steps to prevent recurrence: [action taken]."

## Metrics and Reporting

Support metrics are reviewed weekly in the Monday support standup. Key metrics: first response time (target: under SLA), resolution time (target: under SLA), customer satisfaction score (target: 4.5 out of 5), ticket volume trends, and escalation rate (target: under 10% of tickets escalated to engineering).
