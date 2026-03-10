"""System prompt assembly and context windowing for agent LLM calls."""

from __future__ import annotations

from entwine.agents.models import AgentPersona


def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 characters per token."""
    return len(text) // 4


def build_system_prompt(
    persona: AgentPersona,
    available_tools: list[str] | None = None,
    world_context: str = "",
) -> str:
    """Build a system prompt from persona fields.

    Telegraph style — concise, no filler.
    """
    parts: list[str] = [
        f"You are {persona.name}, {persona.role}.",
        f"Goal: {persona.goal}",
    ]
    if persona.department:
        parts.append(f"Department: {persona.department}")
    if persona.backstory:
        parts.append(f"Backstory: {persona.backstory}")
    if available_tools:
        parts.append(f"Available tools: {', '.join(available_tools)}")
    if world_context:
        parts.append(f"World context: {world_context}")
    return "\n".join(parts)


def assemble_messages(
    system_prompt: str,
    short_term_memory: list[dict],
    current_event: dict | None = None,
    rag_results: list[str] | None = None,
    max_tokens: int = 8000,
) -> list[dict[str, str]]:
    """Assemble OpenAI-format messages list with context windowing.

    Keeps most recent memory entries, truncates oldest when the total
    would exceed *max_tokens*.
    """
    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]

    # Build the user message for the current turn (event + RAG).
    user_parts: list[str] = []
    if current_event is not None:
        user_parts.append(f"Event: {current_event}")
    if rag_results:
        user_parts.append("Retrieved context:\n" + "\n".join(rag_results))
    current_user_msg: dict[str, str] | None = None
    if user_parts:
        current_user_msg = {"role": "user", "content": "\n".join(user_parts)}

    # Budget: subtract system prompt and current user message tokens.
    budget = max_tokens - estimate_tokens(system_prompt)
    if current_user_msg is not None:
        budget -= estimate_tokens(current_user_msg["content"])

    # Fit as many recent memory entries as possible within budget.
    fitted: list[dict] = []
    for entry in reversed(short_term_memory):
        cost = estimate_tokens(entry.get("content", ""))
        if cost > budget:
            break
        fitted.append(entry)
        budget -= cost
    fitted.reverse()

    messages.extend(fitted)

    if current_user_msg is not None:
        messages.append(current_user_msg)

    return messages
