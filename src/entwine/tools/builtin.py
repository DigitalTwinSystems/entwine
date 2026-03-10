"""Built-in tool functions for entwine agents."""

from __future__ import annotations


async def delegate_task(recipient: str, task_description: str, priority: str = "normal") -> str:
    """Delegate a task to another agent."""
    return f"Task delegated to {recipient} with priority={priority}: {task_description}"


async def query_knowledge(query: str, role: str) -> str:
    """Query the knowledge base for information relevant to a role."""
    return f"Knowledge results for role={role}: synthetic answer for '{query}'"


async def read_metrics() -> str:
    """Read current simulation metrics."""
    return "Metrics: agents_active=5, tasks_pending=3, avg_latency_ms=42"
