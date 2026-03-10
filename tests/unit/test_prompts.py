"""Unit tests for system prompt assembly and context windowing."""

from __future__ import annotations

from entwine.agents.models import AgentPersona
from entwine.agents.prompts import assemble_messages, build_system_prompt, estimate_tokens

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_persona(**overrides) -> AgentPersona:
    defaults = {
        "name": "cmo",
        "role": "Chief Marketing Officer",
        "goal": "Drive brand growth",
        "backstory": "20 years in marketing",
        "department": "Marketing",
    }
    defaults.update(overrides)
    return AgentPersona(**defaults)


# ---------------------------------------------------------------------------
# build_system_prompt
# ---------------------------------------------------------------------------


class TestBuildSystemPrompt:
    def test_includes_persona_fields(self) -> None:
        persona = make_persona()
        prompt = build_system_prompt(persona)
        assert "cmo" in prompt
        assert "Chief Marketing Officer" in prompt
        assert "Drive brand growth" in prompt
        assert "Marketing" in prompt
        assert "20 years in marketing" in prompt

    def test_with_tools(self) -> None:
        persona = make_persona()
        prompt = build_system_prompt(persona, available_tools=["send_email", "search"])
        assert "send_email" in prompt
        assert "search" in prompt
        assert "Available tools" in prompt

    def test_with_world_context(self) -> None:
        persona = make_persona()
        prompt = build_system_prompt(persona, world_context="Q1 budget approved")
        assert "Q1 budget approved" in prompt
        assert "World context" in prompt

    def test_omits_empty_optional_fields(self) -> None:
        persona = make_persona(department="", backstory="")
        prompt = build_system_prompt(persona)
        assert "Department" not in prompt
        assert "Backstory" not in prompt

    def test_no_tools_omits_tools_line(self) -> None:
        persona = make_persona()
        prompt = build_system_prompt(persona)
        assert "Available tools" not in prompt


# ---------------------------------------------------------------------------
# assemble_messages
# ---------------------------------------------------------------------------


class TestAssembleMessages:
    def test_basic_case(self) -> None:
        system = "You are a test agent."
        memory = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]
        event = {"type": "meeting", "topic": "Q1"}
        msgs = assemble_messages(system, memory, current_event=event)

        assert msgs[0] == {"role": "system", "content": system}
        assert msgs[1] == memory[0]
        assert msgs[2] == memory[1]
        assert msgs[3]["role"] == "user"
        assert "meeting" in msgs[3]["content"]

    def test_truncates_old_memory(self) -> None:
        system = "Short system."
        # Create memory entries that together exceed the budget.
        # Each entry ~100 chars => ~25 tokens.
        memory = [{"role": "user", "content": "x" * 100} for _ in range(50)]
        msgs = assemble_messages(system, memory, max_tokens=200)

        # System message always present.
        assert msgs[0]["role"] == "system"
        # Should have fewer memory entries than the original 50.
        mem_msgs = [m for m in msgs if m["role"] != "system"]
        assert len(mem_msgs) < 50
        # The kept entries should be the most recent ones.
        assert mem_msgs[-1]["content"] == "x" * 100

    def test_with_rag_results(self) -> None:
        system = "Agent prompt."
        msgs = assemble_messages(
            system,
            short_term_memory=[],
            current_event={"type": "query"},
            rag_results=["doc chunk 1", "doc chunk 2"],
        )
        last = msgs[-1]
        assert last["role"] == "user"
        assert "doc chunk 1" in last["content"]
        assert "doc chunk 2" in last["content"]
        assert "Retrieved context" in last["content"]

    def test_no_event_no_trailing_user_msg(self) -> None:
        system = "Agent prompt."
        msgs = assemble_messages(system, short_term_memory=[], current_event=None)
        # Only system message.
        assert len(msgs) == 1
        assert msgs[0]["role"] == "system"

    def test_memory_order_preserved(self) -> None:
        system = "S"
        memory = [
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "second"},
            {"role": "user", "content": "third"},
        ]
        msgs = assemble_messages(system, memory)
        contents = [m["content"] for m in msgs[1:]]
        assert contents == ["first", "second", "third"]


# ---------------------------------------------------------------------------
# estimate_tokens
# ---------------------------------------------------------------------------


class TestEstimateTokens:
    def test_basic(self) -> None:
        assert estimate_tokens("abcd") == 1
        assert estimate_tokens("abcdefgh") == 2

    def test_empty(self) -> None:
        assert estimate_tokens("") == 0

    def test_rough_approximation(self) -> None:
        text = "a" * 400
        assert estimate_tokens(text) == 100
