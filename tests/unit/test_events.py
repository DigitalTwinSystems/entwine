"""Unit tests for the event bus and event models."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import pytest

from entwine.events import (
    AgentStateChanged,
    Event,
    EventBus,
    MessageSent,
    PlatformAction,
    SystemEvent,
    TaskAssigned,
    TaskCompleted,
)

# ---------------------------------------------------------------------------
# Event model tests
# ---------------------------------------------------------------------------


class TestEventModels:
    def test_event_auto_generates_id(self) -> None:
        e1 = Event(source_agent="ceo", event_type="test")
        e2 = Event(source_agent="ceo", event_type="test")
        assert e1.id != e2.id
        assert len(e1.id) == 36  # UUID4 string length

    def test_event_auto_generates_timestamp(self) -> None:
        before = datetime.now(UTC)
        event = Event(source_agent="ceo", event_type="test")
        after = datetime.now(UTC)
        assert before <= event.timestamp <= after

    def test_event_timestamp_is_utc(self) -> None:
        event = Event(source_agent="ceo", event_type="test")
        assert event.timestamp.tzinfo is not None
        assert event.timestamp.utcoffset().total_seconds() == 0  # type: ignore[union-attr]

    def test_event_default_payload_is_empty_dict(self) -> None:
        event = Event(source_agent="ceo", event_type="test")
        assert event.payload == {}

    def test_event_correlation_id_defaults_to_none(self) -> None:
        event = Event(source_agent="ceo", event_type="test")
        assert event.correlation_id is None

    def test_event_with_all_fields(self) -> None:
        event = Event(
            source_agent="cmo",
            event_type="custom",
            correlation_id="corr-123",
            payload={"key": "value"},
        )
        assert event.source_agent == "cmo"
        assert event.event_type == "custom"
        assert event.correlation_id == "corr-123"
        assert event.payload == {"key": "value"}

    def test_task_assigned_default_event_type(self) -> None:
        e = TaskAssigned(source_agent="ceo", payload={"task": "write report"})
        assert e.event_type == "task_assigned"

    def test_task_completed_default_event_type(self) -> None:
        e = TaskCompleted(source_agent="dev1", payload={"result": "done"})
        assert e.event_type == "task_completed"

    def test_message_sent_default_event_type(self) -> None:
        e = MessageSent(source_agent="cmo", payload={"to": "ceo", "body": "hello"})
        assert e.event_type == "message_sent"

    def test_platform_action_default_event_type(self) -> None:
        e = PlatformAction(source_agent="cmo", payload={"platform": "linkedin"})
        assert e.event_type == "platform_action"

    def test_agent_state_changed_default_event_type(self) -> None:
        e = AgentStateChanged(source_agent="ceo", payload={"from": "READY", "to": "RUNNING"})
        assert e.event_type == "agent_state_changed"

    def test_system_event_default_event_type(self) -> None:
        e = SystemEvent(source_agent="supervisor", payload={"msg": "simulation started"})
        assert e.event_type == "system_event"

    def test_subclass_inherits_auto_id_and_timestamp(self) -> None:
        e1 = TaskAssigned(source_agent="ceo")
        e2 = TaskAssigned(source_agent="ceo")
        assert e1.id != e2.id
        assert isinstance(e1.timestamp, datetime)

    def test_correlation_id_propagation(self) -> None:
        corr = "session-abc-123"
        events: list[Event] = [
            TaskAssigned(source_agent="ceo", correlation_id=corr, payload={"task": "a"}),
            TaskCompleted(source_agent="dev1", correlation_id=corr, payload={"result": "ok"}),
            MessageSent(
                source_agent="cmo",
                correlation_id=corr,
                payload={"to": "ceo", "body": "done"},
            ),
        ]
        for event in events:
            assert event.correlation_id == corr


# ---------------------------------------------------------------------------
# EventBus tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_publish_subscribe_specific_event_type() -> None:
    bus = EventBus()
    await bus.start()

    received: list[Event] = []

    def handler(event: Event) -> None:
        received.append(event)

    bus.subscribe("task_assigned", handler)

    event = TaskAssigned(source_agent="ceo", payload={"task": "write report"})
    await bus.publish(event)
    await bus.stop()

    assert len(received) == 1
    assert received[0].id == event.id
    assert received[0].event_type == "task_assigned"


@pytest.mark.asyncio
async def test_subscribe_does_not_receive_other_event_types() -> None:
    bus = EventBus()
    await bus.start()

    received: list[Event] = []

    def handler(event: Event) -> None:
        received.append(event)

    bus.subscribe("task_assigned", handler)

    await bus.publish(MessageSent(source_agent="cmo", payload={"to": "ceo"}))
    await bus.stop()

    assert received == []


@pytest.mark.asyncio
async def test_subscribe_all_receives_every_event() -> None:
    bus = EventBus()
    await bus.start()

    received: list[Event] = []

    def monitor(event: Event) -> None:
        received.append(event)

    bus.subscribe_all(monitor)

    events_to_publish: list[Event] = [
        TaskAssigned(source_agent="ceo"),
        TaskCompleted(source_agent="dev1"),
        MessageSent(source_agent="cmo"),
        SystemEvent(source_agent="supervisor"),
    ]
    for e in events_to_publish:
        await bus.publish(e)

    await bus.stop()

    assert len(received) == len(events_to_publish)
    published_ids = {e.id for e in events_to_publish}
    received_ids = {e.id for e in received}
    assert published_ids == received_ids


@pytest.mark.asyncio
async def test_subscribe_all_and_specific_both_receive_matching_event() -> None:
    bus = EventBus()
    await bus.start()

    specific: list[Event] = []
    all_events: list[Event] = []

    bus.subscribe("task_assigned", lambda e: specific.append(e))
    bus.subscribe_all(lambda e: all_events.append(e))

    event = TaskAssigned(source_agent="ceo")
    await bus.publish(event)
    await bus.stop()

    assert len(specific) == 1
    assert len(all_events) == 1
    assert specific[0].id == event.id
    assert all_events[0].id == event.id


@pytest.mark.asyncio
async def test_async_handler_is_awaited() -> None:
    bus = EventBus()
    await bus.start()

    received: list[Event] = []

    async def async_handler(event: Event) -> None:
        await asyncio.sleep(0)
        received.append(event)

    bus.subscribe("system_event", async_handler)

    event = SystemEvent(source_agent="supervisor", payload={"msg": "tick"})
    await bus.publish(event)
    await bus.stop()

    assert len(received) == 1
    assert received[0].id == event.id


@pytest.mark.asyncio
async def test_correlation_id_preserved_through_bus() -> None:
    bus = EventBus()
    await bus.start()

    received: list[Event] = []

    def handler(event: Event) -> None:
        received.append(event)

    bus.subscribe_all(handler)

    corr = "corr-xyz-789"
    event = TaskAssigned(source_agent="ceo", correlation_id=corr)
    await bus.publish(event)
    await bus.stop()

    assert len(received) == 1
    assert received[0].correlation_id == corr


@pytest.mark.asyncio
async def test_handler_exception_does_not_stop_bus() -> None:
    bus = EventBus()
    await bus.start()

    good_received: list[Event] = []

    def bad_handler(event: Event) -> None:
        raise RuntimeError("intentional failure")

    def good_handler(event: Event) -> None:
        good_received.append(event)

    bus.subscribe("task_assigned", bad_handler)
    bus.subscribe("task_assigned", good_handler)

    await bus.publish(TaskAssigned(source_agent="ceo"))
    await bus.stop()

    # good_handler must still have run despite bad_handler raising
    assert len(good_received) == 1


@pytest.mark.asyncio
async def test_multiple_subscribers_for_same_event_type() -> None:
    bus = EventBus()
    await bus.start()

    bucket_a: list[Event] = []
    bucket_b: list[Event] = []

    bus.subscribe("message_sent", lambda e: bucket_a.append(e))
    bus.subscribe("message_sent", lambda e: bucket_b.append(e))

    event = MessageSent(source_agent="cmo", payload={"to": "ceo"})
    await bus.publish(event)
    await bus.stop()

    assert len(bucket_a) == 1
    assert len(bucket_b) == 1
    assert bucket_a[0].id == bucket_b[0].id


@pytest.mark.asyncio
async def test_start_already_running_is_noop() -> None:
    """Starting a bus that is already running should log a warning and be a no-op."""
    bus = EventBus()
    await bus.start()
    # Second start should not raise.
    await bus.start()
    # The bus should still work normally.
    received: list[Event] = []
    bus.subscribe_all(lambda e: received.append(e))
    await bus.publish(TaskAssigned(source_agent="ceo"))
    await bus.stop()
    assert len(received) == 1


@pytest.mark.asyncio
async def test_stop_is_idempotent() -> None:
    bus = EventBus()
    await bus.start()
    await bus.stop()
    # Second stop must not raise
    await bus.stop()


@pytest.mark.asyncio
async def test_payload_contents_preserved() -> None:
    bus = EventBus()
    await bus.start()

    received: list[Event] = []
    bus.subscribe_all(lambda e: received.append(e))

    payload: dict[str, Any] = {"task": "draft post", "platform": "linkedin", "priority": 1}
    event = PlatformAction(source_agent="cmo", payload=payload)
    await bus.publish(event)
    await bus.stop()

    assert received[0].payload == payload
