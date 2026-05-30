"""Tests for adapter live-mode wiring (attach_supervisor + threaded run)."""

from __future__ import annotations

import time

import pytest

from fakes import FakeMpcController, FakePlcLink, make_cycle
from plc_workflows_mpc import PlcWorkflowsMpcAdapter
from plc_workflows_mpc.config import TagMap
from plc_workflows_mpc.supervisor import (
    HeartbeatLinkHealth,
    SupervisorConfig,
    SupervisorRunner,
)


def _build_supervisor(adapter: PlcWorkflowsMpcAdapter) -> SupervisorRunner:
    """Build a live SupervisorRunner whose record_sink feeds the adapter queue."""
    cycles = [
        make_cycle(enabled=True, hb=i + 1, mv_feedback=0.0, cv=(0.0,)) for i in range(200)
    ]
    return SupervisorRunner(
        config=SupervisorConfig(
            control_period_s=0.0, poll_s=0.01, dry_run=True, equipment_id="EQ-X", loop_id="L-1"
        ),
        tags=TagMap(),
        plc_link=FakePlcLink(cycles=cycles),
        controller=FakeMpcController(constant_move=0.25),
        health=HeartbeatLinkHealth(heartbeat_timeout_s=2.0, rearm_holdoff_s=0.0),
        record_sink=adapter.queue_record,
    )


@pytest.fixture
def adapter():
    return PlcWorkflowsMpcAdapter()


async def test_attach_and_start_launches_supervisor_thread(adapter):
    sup = _build_supervisor(adapter)
    adapter.attach_supervisor(sup)
    await adapter.configure({})
    await adapter.start()
    # Give the supervisor a moment to enter RUNNING and emit at least one record.
    deadline = time.monotonic() + 2.0
    while not [r async for r in _peek(adapter)] and time.monotonic() < deadline:
        time.sleep(0.05)
    await adapter.stop()


async def _peek(adapter):
    """Yield whatever is currently in the queue, then return — not blocking."""
    async for record in adapter.collect():
        yield record


async def test_live_records_flow_through_collect(adapter):
    sup = _build_supervisor(adapter)
    adapter.attach_supervisor(sup)
    await adapter.configure({})
    await adapter.start()

    # Wait for supervisor to push records.
    deadline = time.monotonic() + 3.0
    records = []
    while time.monotonic() < deadline:
        async for rec in adapter.collect():
            records.append(rec)
        if any(r.context.extra.get("event_type") == "control_move" for r in records):
            break
        time.sleep(0.05)

    await adapter.stop()

    control_moves = [r for r in records if r.context.extra.get("event_type") == "control_move"]
    assert control_moves, "supervisor should have emitted at least one control_move record"
    move = control_moves[0]
    assert move.context.equipment_id == "EQ-X"
    assert move.context.extra["loop_id"] == "L-1"
    assert move.context.extra["controller_type"] == "MPC"
    assert move.value.raw == 0.25


async def test_stop_joins_supervisor_thread(adapter):
    sup = _build_supervisor(adapter)
    adapter.attach_supervisor(sup)
    await adapter.configure({})
    await adapter.start()
    thread = adapter._supervisor_thread  # noqa: SLF001 — test inspection
    assert thread is not None and thread.is_alive()
    await adapter.stop()
    # After stop(), the thread should be joined and not alive.
    assert not thread.is_alive()


async def test_write_routes_to_plc_link_in_live_mode(adapter):
    sup = _build_supervisor(adapter)
    adapter.attach_supervisor(sup)
    await adapter.configure({})
    await adapter.start()
    ok = await adapter.write("MPC_Temp_SP", 42.0)
    assert ok is True
    # The supervisor's fake PLC link should have recorded our write.
    plc = sup.plc_link
    assert ("MPC_Temp_SP", 42.0) in plc.writes  # type: ignore[attr-defined]
    await adapter.stop()


async def test_inject_only_mode_still_works_without_supervisor(adapter):
    await adapter.configure({})
    await adapter.start()
    adapter.inject_records(
        [
            {
                "equipment_id": "FERM-003",
                "loop_id": "TIC-101",
                "controller_type": "MPC",
                "mv_tag": "TIC-101.OUT",
                "event_type": "control_move",
                "value": 1.23,
                "timestamp": "2026-05-30T12:00:00Z",
            }
        ]
    )
    records = [r async for r in adapter.collect()]
    await adapter.stop()
    assert len(records) == 1
    assert records[0].value.raw == 1.23


