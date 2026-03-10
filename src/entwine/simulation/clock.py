"""Simulation clock that tracks simulated time independent of wall clock."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import structlog

from entwine.agents.models import WorkingHours

logger = structlog.get_logger(__name__)


class SimulationClock:
    """A discrete-tick simulation clock.

    Each call to :meth:`tick` advances simulated time by
    ``tick_interval_seconds * speed_multiplier`` seconds.  The clock is
    completely decoupled from wall-clock time.
    """

    def __init__(
        self,
        speed_multiplier: float = 1.0,
        start_hour: float = 9.0,
        tick_interval_seconds: float = 60.0,
    ) -> None:
        self._speed_multiplier = speed_multiplier
        self._tick_interval_seconds = tick_interval_seconds

        # Build an initial simulated datetime anchored at today with the
        # requested starting hour.
        hour = int(start_hour)
        minute = int((start_hour - hour) * 60)
        now = datetime.now(UTC)
        self._current_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

        self._elapsed_ticks: int = 0
        self._is_running: bool = False

        logger.info(
            "clock_created",
            speed_multiplier=speed_multiplier,
            start_hour=start_hour,
            tick_interval_seconds=tick_interval_seconds,
        )

    # -- properties -----------------------------------------------------------

    @property
    def current_time(self) -> datetime:
        """Return the current simulated datetime (UTC)."""
        return self._current_time

    @property
    def current_hour(self) -> float:
        """Return the current simulated hour as a float in [0, 24)."""
        return self._current_time.hour + self._current_time.minute / 60.0

    @property
    def elapsed_ticks(self) -> int:
        """Return the number of ticks that have been executed."""
        return self._elapsed_ticks

    @property
    def is_running(self) -> bool:
        """Return whether the clock is currently running."""
        return self._is_running

    # -- control --------------------------------------------------------------

    def start(self) -> None:
        """Start the clock, allowing :meth:`tick` to advance time."""
        self._is_running = True
        logger.info("clock_started", current_time=self._current_time.isoformat())

    def stop(self) -> None:
        """Stop the clock.  Subsequent calls to :meth:`tick` are no-ops."""
        self._is_running = False
        logger.info(
            "clock_stopped",
            current_time=self._current_time.isoformat(),
            elapsed_ticks=self._elapsed_ticks,
        )

    def tick(self) -> None:
        """Advance simulated time by one tick.

        The time delta equals ``tick_interval_seconds * speed_multiplier``.
        Does nothing if the clock has not been started.
        """
        if not self._is_running:
            return

        delta = timedelta(seconds=self._tick_interval_seconds * self._speed_multiplier)
        self._current_time += delta
        self._elapsed_ticks += 1

        logger.debug(
            "clock_tick",
            tick=self._elapsed_ticks,
            simulated_time=self._current_time.isoformat(),
        )

    # -- queries --------------------------------------------------------------

    def is_within_working_hours(self, working_hours: WorkingHours) -> bool:
        """Check whether the current simulated hour is within *working_hours*.

        The comparison uses the ``start`` and ``end`` fields of *working_hours*
        (``"HH:MM"`` strings) converted to float hours.
        """
        start_parts = working_hours.start.split(":")
        start_h = int(start_parts[0]) + int(start_parts[1]) / 60.0

        end_parts = working_hours.end.split(":")
        end_h = int(end_parts[0]) + int(end_parts[1]) / 60.0

        return start_h <= self.current_hour < end_h
