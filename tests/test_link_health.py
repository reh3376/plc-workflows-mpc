"""Tests for the heartbeat-based PLC link health monitor."""

from __future__ import annotations

import pytest

from plc_workflows_mpc.supervisor.health import HeartbeatLinkHealth


def test_unhealthy_initially_until_heartbeat_advances():
    h = HeartbeatLinkHealth(heartbeat_timeout_s=2.0, rearm_holdoff_s=5.0)
    healthy, stable = h.update(plc_heartbeat=0, io_ok=True, now=0.0)
    assert healthy is True  # first call: last_change just set to now
    assert stable is False


def test_io_failure_collapses_health_and_stability():
    h = HeartbeatLinkHealth(heartbeat_timeout_s=2.0, rearm_holdoff_s=1.0)
    h.update(0, True, 0.0)
    h.update(1, True, 0.5)
    healthy, stable = h.update(1, True, 1.2)  # holdoff passed
    assert (healthy, stable) == (True, True)
    healthy, stable = h.update(1, False, 1.3)
    assert (healthy, stable) == (False, False)


def test_stable_after_holdoff_with_advancing_heartbeat():
    h = HeartbeatLinkHealth(heartbeat_timeout_s=2.0, rearm_holdoff_s=3.0)
    h.update(0, True, 0.0)
    h.update(1, True, 1.0)
    h.update(2, True, 2.0)
    healthy, stable = h.update(3, True, 3.0)
    # Healthy_since was set at t=0; holdoff is 3.0; at t=3.0 stable should be True.
    assert healthy is True
    assert stable is True


def test_frozen_heartbeat_eventually_unhealthy():
    h = HeartbeatLinkHealth(heartbeat_timeout_s=2.0, rearm_holdoff_s=1.0)
    h.update(5, True, 0.0)
    # Heartbeat hasn't advanced; after 2.5 s past the timeout we go unhealthy.
    healthy, stable = h.update(5, True, 2.5)
    assert healthy is False
    assert stable is False


def test_seconds_until_rearm_counts_down():
    h = HeartbeatLinkHealth(heartbeat_timeout_s=2.0, rearm_holdoff_s=10.0)
    assert h.seconds_until_rearm(0.0) is None
    h.update(0, True, 0.0)
    assert h.seconds_until_rearm(0.0) == pytest.approx(10.0)
    h.update(1, True, 4.0)
    assert h.seconds_until_rearm(4.0) == pytest.approx(6.0)
    # Lose link: resets to None.
    h.update(1, False, 5.0)
    assert h.seconds_until_rearm(5.0) is None


def test_invalid_constructor_args():
    with pytest.raises(ValueError):
        HeartbeatLinkHealth(heartbeat_timeout_s=0.0, rearm_holdoff_s=1.0)
    with pytest.raises(ValueError):
        HeartbeatLinkHealth(heartbeat_timeout_s=1.0, rearm_holdoff_s=-1.0)
