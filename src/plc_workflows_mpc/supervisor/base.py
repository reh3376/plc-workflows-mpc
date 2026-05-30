"""Public types for the supervisor package — extracted to avoid circular imports."""

from __future__ import annotations

import abc
from enum import Enum, auto


class Mode(Enum):
    """Supervisor control modes."""

    IDLE = auto()
    ARMING = auto()
    RUNNING = auto()


class LinkHealth(abc.ABC):
    """Tracks PLC link liveness and the re-arm hold-off."""

    @abc.abstractmethod
    def update(self, plc_heartbeat: int, io_ok: bool, now: float) -> tuple[bool, bool]:
        """Update from the latest heartbeat / IO status.

        Returns ``(healthy, stable)`` where ``healthy`` means the PLC heartbeat
        is advancing within the timeout, and ``stable`` means it has stayed
        healthy long enough to (re)arm.
        """


class SupervisorService(abc.ABC):
    """The IDLE/ARMING/RUNNING control loop."""

    @property
    @abc.abstractmethod
    def mode(self) -> Mode:
        """Current control mode."""

    @abc.abstractmethod
    def step(self, now: float) -> None:
        """Run one control/poll iteration."""

    @abc.abstractmethod
    def run_forever(self) -> None:
        """Run the control loop until ``stop()`` is called or interrupted."""

    @abc.abstractmethod
    def stop(self) -> None:
        """Signal the control loop to exit cleanly."""


__all__ = ["Mode", "LinkHealth", "SupervisorService"]
