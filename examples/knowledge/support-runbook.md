---
department: support
accessible_roles: customer support engineer, cto, developer, devops
sensitivity: internal
---

# Customer Support Runbook

## Ticket Triage

| Priority | Response SLA | Resolution SLA | Examples |
|----------|-------------|----------------|----------|
| P0 — Critical | 15 min | 4 hours | Service outage, data loss |
| P1 — High | 1 hour | 8 hours | Feature broken, workaround available |
| P2 — Medium | 4 hours | 48 hours | Non-blocking bug, UI glitch |
| P3 — Low | 24 hours | 5 business days | Feature request, docs clarification |

## Common Issues & Resolution

### Authentication Failures (P1)

**Symptoms**: User cannot log in, SSO redirect loop, "Invalid token" error.

**Steps**:
1. Check if the issue is user-specific or platform-wide (Grafana dashboard: auth-errors).
2. If platform-wide: escalate to on-call engineer immediately.
3. If user-specific: verify SSO config in admin panel → check token expiry → clear session cache.
4. If persistent: regenerate API key and notify the user.

### Slow Search Performance (P2)

**Symptoms**: Search queries taking > 2s, timeout errors on large workspaces.

**Steps**:
1. Check Qdrant health: `curl http://qdrant:6333/readyz`
2. Check index status: `curl http://qdrant:6333/collections/enterprise_knowledge`
3. If collection is large (>1M vectors): check if HNSW index is rebuilding (can take 5-10 min).
4. If persistent: file GitHub issue with query examples and response times.

### Webhook Delivery Failures (P2)

**Symptoms**: Customer reports missing webhook events, retry queue growing.

**Steps**:
1. Check webhook delivery logs in admin panel (Settings → Webhooks → Delivery History).
2. Verify customer endpoint is reachable: `curl -I <endpoint_url>`
3. If 4xx: customer config issue — share error details.
4. If 5xx or timeout: retry manually. If persistent, check for rate-limiting.

## Escalation Path

1. **L1 Support** (Tariq): Initial triage, known-issue resolution.
2. **Engineering On-Call**: P0/P1 escalation, unknown bugs.
3. **CTO** (David): Architecture-level issues, customer-impacting outages.
4. **CEO** (Alice): Customer relationship issues, SLA breach communication.
