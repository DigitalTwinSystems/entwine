"""Built-in tool functions for entwine agents."""

from __future__ import annotations


async def delegate_task(recipient: str, task_description: str, priority: str = "normal") -> str:
    """Delegate a task to another agent."""
    return f"Task delegated to {recipient} with priority={priority}: {task_description}"


async def query_knowledge(query: str, role: str) -> str:
    """Query the knowledge base for information relevant to a role."""
    return f"Knowledge results for role={role}: synthetic answer for '{query}'"


async def read_company_metrics() -> str:
    """Read current company and simulation metrics."""
    return "Metrics: agents_active=12, tasks_pending=8, avg_latency_ms=42, revenue_mrr=250000"


async def schedule_meeting(attendees: str, time: str, agenda: str) -> str:
    """Schedule a meeting with specified attendees."""
    return f"Meeting scheduled at {time} with {attendees}. Agenda: {agenda}"


async def draft_email(to: str, subject: str, body: str) -> str:
    """Draft an email message."""
    return f"Email drafted to {to}. Subject: {subject}"


async def post_to_slack(channel: str, message: str) -> str:
    """Post a message to a Slack channel."""
    return f"Posted to {channel}: {message[:80]}"


async def post_to_linkedin(content: str) -> str:
    """Publish a post to LinkedIn."""
    return f"LinkedIn post published: {content[:80]}"


async def post_to_x(content: str) -> str:
    """Publish a post to X (Twitter)."""
    return f"Posted to X: {content[:80]}"


async def create_github_issue(title: str, body: str, labels: str = "") -> str:
    """Create a GitHub issue."""
    return f"GitHub issue created: '{title}' labels=[{labels}]"


async def create_pr(title: str, body: str, branch: str) -> str:
    """Create a GitHub pull request."""
    return f"PR created: '{title}' from branch {branch}"


async def read_crm(query: str) -> str:
    """Query the CRM system for customer or deal information."""
    return f"CRM results for '{query}': 3 matching records found"


async def update_crm_ticket(ticket_id: str, status: str, note: str = "") -> str:
    """Update the status of a CRM ticket."""
    return f"Ticket {ticket_id} updated to status={status}" + (f" note: {note}" if note else "")
