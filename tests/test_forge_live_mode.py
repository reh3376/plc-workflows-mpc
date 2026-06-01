"""Forge-integration tests — supervisor → adapter → hub end-to-end.

Verifies that records produced by the live supervisory control runtime
(``SupervisorRunner`` driving an ``MpcController`` over a ``PlcLink``) flow
all the way through the adapter, get streamed via ``GrpcTransportAdapter``,
and land in the hub-side servicer's queue with the right shape. Two
variants: deterministic (manual ``step``) and threaded (``run_forever``
in a daemon thread).
"""

from __future__ import annotations

import time

import pytest

from fakes import FakeMpcController, FakePlcLink, make_cycle
from harness import FakeForgeHub
from plc_workflows_mpc import PlcWorkflowsMpcAdapter
from plc_workflows_mpc.config import TagMap
from plc_workflows_mpc.supervisor import (
    HeartbeatLinkHealth,
    SupervisorConfig,
    SupervisorRunner,
)


def _build_supervisor(adapter: PlcWorkflowsMpcAdapter) -> tuple[SupervisorRunner, FakePlcLink]:
    cycles = [
        make_cycle(enabled=True, hb=i + 1, mv_feedback=10.0, cv=(20.0,)) for i in range(50)
    ]
    plc = FakePlcLink(cycles=cycles)
    sup = SupervisorRunner(
        config=SupervisorConfig(
            control_period_s=0.0,
            poll_s=0.005,
            dry_run=True,
            equipment_id="FERM-003",
            loop_id="TIC-101",
            area="Fermentation",
            site="Plant1",
        ),
        tags=TagMap(),
        plc_link=plc,
        controller=FakeMpcController(constant_move=0.25),
        health=HeartbeatLinkHealth(heartbeat_timeout_s=2.0, rearm_holdoff_s=0.0),
        record_sink=adapter.queue_record,
    )
    return sup, plc


async def test_manual_supervisor_steps_reach_the_hub():
    """Driving the supervisor's ``step`` manually lets us assert exactly which
    records arrive on the hub side after each cycle."""
    adapter = PlcWorkflowsMpcAdapter()
    sup, _plc = _build_supervisor(adapter)
    async with FakeForgeHub.over(adapter) as hub:
        await hub.run_lifecycle()
        # IDLE → ARMING (enable was set in the first cycle).
        sup.step(now=0.0)
        # ARMING → RUNNING (rearm_holdoff is 0 so the next healthy step arms).
        sup.step(now=0.1)
        # RUNNING — one control_move per call thereafter.
        sup.step(now=0.2)
        sup.step(now=0.3)

        sent = await hub.stream_once()
        received = await hub.received_records()

    assert sent == len(received)
    event_types = [r.context.extra.get("event_type") for r in received]
    assert "mode_change" in event_types
    assert "control_move" in event_types

    moves = [r for r in received if r.context.extra.get("event_type") == "control_move"]
    move = moves[0]
    assert move.context.equipment_id == "FERM-003"
    assert move.context.area == "Fermentation"
    assert move.context.extra["loop_id"] == "TIC-101"
    assert move.context.extra["controller_type"] == "MPC"
    assert move.value.raw == 0.25


async def test_threaded_supervisor_run_reaches_the_hub_and_stops_cleanly():
    """attach_supervisor + adapter.start spawns the supervisor in a thread;
    its records must reach the hub when we drain via ``stream_once``."""
    adapter = PlcWorkflowsMpcAdapter()
    sup, _plc = _build_supervisor(adapter)
    adapter.attach_supervisor(sup)

    async with FakeForgeHub.over(adapter) as hub:
        await hub.run_lifecycle()
        # The adapter's start() (called by run_lifecycle through the transport)
        # spawns the supervisor's run_forever in a daemon thread.
        deadline = time.monotonic() + 3.0
        moves_seen = 0
        # Poll until we've collected at least one control_move, or time out.
        while moves_seen == 0 and time.monotonic() < deadline:
            await hub.stream_once()
            received = await hub.received_records()
            moves_seen = sum(
                1 for r in received if r.context.extra.get("event_type") == "control_move"
            )
            if moves_seen == 0:
                time.sleep(0.05)

    assert moves_seen >= 1, "expected at least one control_move from the running supervisor"
    # After __aexit__, the adapter's stop() should have joined the supervisor thread.
    assert adapter._supervisor_thread is None  # noqa: SLF001 — explicit teardown check


async def test_dry_run_supervisor_does_not_write_to_plc_even_under_load():
    """Smoke: the supervisor's ``dry_run=True`` setting must hold even when
    its records are being streamed to a hub."""
    adapter = PlcWorkflowsMpcAdapter()
    sup, plc = _build_supervisor(adapter)
    async with FakeForgeHub.over(adapter) as hub:
        await hub.run_lifecycle()
        for now in (0.0, 0.05, 0.1, 0.15, 0.2):
            sup.step(now=now)
        await hub.stream_once()

    # No setpoint writes should have been performed in dry-run mode.
    tags = TagMap()
    setpoint_writes = [v for tag, v in plc.writes if tag == tags.mv_setpoint]
    assert setpoint_writes == []


@pytest.mark.parametrize("n_moves", [3, 7])
async def test_high_cardinality_records_round_trip_in_order(n_moves: int):
    """Sanity: many records survive the full pipeline and arrive in order."""
    adapter = PlcWorkflowsMpcAdapter()
    payloads = [
        {
            "equipment_id": "FERM-003",
            "loop_id": "TIC-101",
            "controller_type": "MPC",
            "mv_tag": "TIC-101.OUT",
            "event_type": "control_move",
            "value": float(i),
            "timestamp": "2026-06-01T12:00:00Z",
        }
        for i in range(n_moves)
    ]
    async with FakeForgeHub.over(adapter) as hub:
        await hub.run_lifecycle()
        adapter.inject_records(payloads)
        sent = await hub.stream_once()
        received = await hub.received_records()

    assert sent == n_moves
    assert [r.value.raw for r in received] == [float(i) for i in range(n_moves)]


