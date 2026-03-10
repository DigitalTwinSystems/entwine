"""Unit tests for the SimulationClock."""

from __future__ import annotations

from datetime import timedelta

from entsim.agents.models import WorkingHours
from entsim.simulation.clock import SimulationClock

# ---------------------------------------------------------------------------
# Initial state
# ---------------------------------------------------------------------------


class TestInitialState:
    def test_default_start_hour(self) -> None:
        clock = SimulationClock()
        assert clock.current_hour == 9.0

    def test_custom_start_hour(self) -> None:
        clock = SimulationClock(start_hour=14.5)
        assert clock.current_hour == 14.5

    def test_elapsed_ticks_starts_at_zero(self) -> None:
        clock = SimulationClock()
        assert clock.elapsed_ticks == 0

    def test_is_not_running_initially(self) -> None:
        clock = SimulationClock()
        assert clock.is_running is False

    def test_current_time_is_datetime(self) -> None:
        clock = SimulationClock()
        assert clock.current_time.tzinfo is not None


# ---------------------------------------------------------------------------
# Tick behaviour
# ---------------------------------------------------------------------------


class TestTick:
    def test_tick_advances_time(self) -> None:
        clock = SimulationClock(tick_interval_seconds=60.0)
        clock.start()
        before = clock.current_time
        clock.tick()
        assert clock.current_time == before + timedelta(seconds=60.0)

    def test_tick_increments_elapsed(self) -> None:
        clock = SimulationClock()
        clock.start()
        clock.tick()
        clock.tick()
        assert clock.elapsed_ticks == 2

    def test_tick_is_noop_when_stopped(self) -> None:
        clock = SimulationClock()
        before = clock.current_time
        clock.tick()
        assert clock.current_time == before
        assert clock.elapsed_ticks == 0


# ---------------------------------------------------------------------------
# Speed multiplier
# ---------------------------------------------------------------------------


class TestSpeedMultiplier:
    def test_speed_multiplier_doubles_time(self) -> None:
        clock = SimulationClock(speed_multiplier=2.0, tick_interval_seconds=60.0)
        clock.start()
        before = clock.current_time
        clock.tick()
        assert clock.current_time == before + timedelta(seconds=120.0)

    def test_speed_multiplier_half(self) -> None:
        clock = SimulationClock(speed_multiplier=0.5, tick_interval_seconds=60.0)
        clock.start()
        before = clock.current_time
        clock.tick()
        assert clock.current_time == before + timedelta(seconds=30.0)


# ---------------------------------------------------------------------------
# Working hours
# ---------------------------------------------------------------------------


class TestWorkingHours:
    def test_within_default_working_hours(self) -> None:
        clock = SimulationClock(start_hour=12.0)
        wh = WorkingHours()
        assert clock.is_within_working_hours(wh) is True

    def test_outside_working_hours_before(self) -> None:
        clock = SimulationClock(start_hour=7.0)
        wh = WorkingHours()
        assert clock.is_within_working_hours(wh) is False

    def test_outside_working_hours_after(self) -> None:
        clock = SimulationClock(start_hour=18.0)
        wh = WorkingHours()
        assert clock.is_within_working_hours(wh) is False

    def test_at_start_boundary_is_inside(self) -> None:
        clock = SimulationClock(start_hour=9.0)
        wh = WorkingHours()
        assert clock.is_within_working_hours(wh) is True

    def test_at_end_boundary_is_outside(self) -> None:
        clock = SimulationClock(start_hour=17.0)
        wh = WorkingHours()
        assert clock.is_within_working_hours(wh) is False

    def test_custom_working_hours(self) -> None:
        clock = SimulationClock(start_hour=22.0)
        wh = WorkingHours(start="20:00", end="23:00")
        assert clock.is_within_working_hours(wh) is True

    def test_half_hour_boundary(self) -> None:
        clock = SimulationClock(start_hour=9.5)
        wh = WorkingHours(start="09:30", end="10:00")
        assert clock.is_within_working_hours(wh) is True


# ---------------------------------------------------------------------------
# Start / Stop
# ---------------------------------------------------------------------------


class TestStartStop:
    def test_start_sets_running(self) -> None:
        clock = SimulationClock()
        clock.start()
        assert clock.is_running is True

    def test_stop_clears_running(self) -> None:
        clock = SimulationClock()
        clock.start()
        clock.stop()
        assert clock.is_running is False

    def test_tick_after_stop_is_noop(self) -> None:
        clock = SimulationClock()
        clock.start()
        clock.tick()
        clock.stop()
        before = clock.current_time
        clock.tick()
        assert clock.current_time == before
        assert clock.elapsed_ticks == 1

    def test_restart_allows_ticking(self) -> None:
        clock = SimulationClock()
        clock.start()
        clock.tick()
        clock.stop()
        clock.start()
        clock.tick()
        assert clock.elapsed_ticks == 2
