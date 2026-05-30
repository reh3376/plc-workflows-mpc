"""Supervisory control runtime — the event-gated state machine.

Ties the PLC link, link-health watchdog, and MPC controller into the
advisory control loop proven in the mpc-supervisor reference:

    IDLE      enable bit clear; only pulse our heartbeat.
    ARMING    enable set, but wait until the PLC link has been continuously
              healthy for the re-arm hold-off before taking the loop.
    RUNNING   we own the loop: estimate → solve → write the setpoint at the
              control period, bumplessly handed over on entry.

Safety: the PLC independently watchdogs *our* heartbeat and hard-clamps any
setpoint, so if this process dies, hangs, or loses the network the controller
reverts to local PID with no cooperation from us. This layer only governs how
cautiously control is handed back *out*.

Phase 2 ships the concrete :class:`HeartbeatLinkHealth` and
:class:`SupervisorRunner`; the public ABCs (:class:`Mode`, :class:`LinkHealth`,
:class:`SupervisorService`) remain for custom implementations.
"""

from __future__ import annotations

from plc_workflows_mpc.supervisor.base import LinkHealth, Mode, SupervisorService
from plc_workflows_mpc.supervisor.health import HeartbeatLinkHealth
from plc_workflows_mpc.supervisor.service import SupervisorConfig, SupervisorRunner

__all__ = [
    "Mode",
    "LinkHealth",
    "SupervisorService",
    "HeartbeatLinkHealth",
    "SupervisorConfig",
    "SupervisorRunner",
]
