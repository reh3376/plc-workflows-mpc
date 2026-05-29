"""Supervisory control runtime — the event-gated state machine.

Ties the PLC link, link-health watchdog, and MPC controller into the
advisory control loop proven in the mpc-supervisor reference:

    IDLE      enable bit clear; only pulse our heartbeat.
    ARMING    enable set, but wait until the PLC link has been continuously
              healthy for the re-arm hold-off before taking the loop
              (anti-flap / auto-revert guard).
    RUNNING   we own the loop: estimate → solve → write the setpoint at the
              control period, bumplessly handed over on entry.

Safety: the PLC independently watchdogs *our* heartbeat and hard-clamps any
setpoint, so if this process dies, hangs, or loses the network the controller
reverts to local PID with no cooperation from us. This layer only governs how
cautiously control is handed back *out*.

Phase 2 implements these; Phase 0 defines the contract.
"""

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
        """Update from the latest heartbeat/IO status.

        Returns ``(healthy, stable)`` where ``healthy`` means the PLC heartbeat
        is advancing within the timeout and ``stable`` means it has stayed
        healthy long enough to (re)arm.
        """


class SupervisorService(abc.ABC):
    """The IDLE/ARMING/RUNNING control loop."""

    @abc.abstractmethod
    def step(self, now: float) -> None:
        """Run one control/poll iteration."""

    @abc.abstractmethod
    def run_forever(self) -> None:
        """Run the control loop until interrupted, releasing control on exit."""


__all__ = ["Mode", "LinkHealth", "SupervisorService"]
