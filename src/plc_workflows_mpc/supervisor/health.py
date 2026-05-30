"""Heartbeat-based PLC link health monitor with anti-flap re-arm hold-off.

Answers two questions per cycle:

* **healthy** — is the PLC heartbeat currently advancing (link + controller alive)?
* **stable** — has it been healthy *continuously* for ≥ the hold-off seconds,
  so the supervisor is allowed to (re)arm?

Any IO failure or frozen heartbeat collapses ``stable`` back to ``False`` and
restarts the hold-off, which is what prevents control flapping on an
intermittent fault. Mirrors the proven mpc-supervisor reference.
"""

from __future__ import annotations

from plc_workflows_mpc.supervisor.base import LinkHealth


class HeartbeatLinkHealth(LinkHealth):
    """Default :class:`LinkHealth` based on a monotonically-advancing tag."""

    def __init__(self, *, heartbeat_timeout_s: float, rearm_holdoff_s: float) -> None:
        if heartbeat_timeout_s <= 0.0:
            raise ValueError("heartbeat_timeout_s must be positive")
        if rearm_holdoff_s < 0.0:
            raise ValueError("rearm_holdoff_s must be non-negative")
        self._timeout = heartbeat_timeout_s
        self._holdoff = rearm_holdoff_s
        self._last_val: int | None = None
        self._last_change: float = 0.0
        self._healthy_since: float | None = None

    def update(self, plc_heartbeat: int, io_ok: bool, now: float) -> tuple[bool, bool]:
        if not io_ok:
            self._healthy_since = None
            return False, False

        if plc_heartbeat != self._last_val:
            self._last_val = plc_heartbeat
            self._last_change = now

        healthy = (now - self._last_change) <= self._timeout
        if healthy:
            if self._healthy_since is None:
                self._healthy_since = now
        else:
            self._healthy_since = None

        stable = self._healthy_since is not None and (now - self._healthy_since) >= self._holdoff
        return healthy, stable

    def seconds_until_rearm(self, now: float) -> float | None:
        """Return seconds until ``stable`` flips True (``None`` if unhealthy)."""
        if self._healthy_since is None:
            return None
        return max(0.0, self._holdoff - (now - self._healthy_since))


__all__ = ["HeartbeatLinkHealth"]
