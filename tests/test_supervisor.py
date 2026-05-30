"""Tests for the SupervisorRunner state machine."""

from __future__ import annotations

from fakes import FakeMpcController, FakePlcLink, make_cycle
from plc_workflows_mpc.config import TagMap
from plc_workflows_mpc.supervisor import (
    HeartbeatLinkHealth,
    Mode,
    SupervisorConfig,
    SupervisorRunner,
)


def _make_supervisor(
    *,
    cycles: list,
    control_period_s: float = 5.0,
    rearm_holdoff_s: float = 1.0,
    dry_run: bool = True,
    sp_min: float | None = None,
    sp_max: float | None = None,
    constant_move: float = 0.5,
) -> tuple[SupervisorRunner, FakePlcLink, FakeMpcController, list[dict]]:
    tags = TagMap()
    plc = FakePlcLink(cycles=cycles)
    ctrl = FakeMpcController(constant_move=constant_move)
    health = HeartbeatLinkHealth(
        heartbeat_timeout_s=2.0, rearm_holdoff_s=rearm_holdoff_s
    )
    records: list[dict] = []
    sup = SupervisorRunner(
        config=SupervisorConfig(
            control_period_s=control_period_s,
            poll_s=0.25,
            dry_run=dry_run,
            sp_min=sp_min,
            sp_max=sp_max,
            equipment_id="EQ-1",
            loop_id="TIC-1",
        ),
        tags=tags,
        plc_link=plc,
        controller=ctrl,
        health=health,
        record_sink=records.append,
    )
    return sup, plc, ctrl, records


def test_starts_idle():
    sup, *_ = _make_supervisor(cycles=[])
    assert sup.mode is Mode.IDLE


def test_idle_to_arming_when_enable_set():
    sup, *_, records = _make_supervisor(
        cycles=[make_cycle(enabled=True, hb=1)],
    )
    sup.step(now=0.0)
    assert sup.mode is Mode.ARMING
    assert any(r["event_type"] == "mode_change" and r["value"] == "ARMING" for r in records)


def test_arming_to_running_after_holdoff_with_bumpless_reset():
    cycles = [
        make_cycle(enabled=True, hb=1, mv_feedback=42.0, cv=(50.0,)),
        make_cycle(enabled=True, hb=2, mv_feedback=42.0, cv=(50.0,)),
        make_cycle(enabled=True, hb=3, mv_feedback=42.0, cv=(50.0,)),
    ]
    sup, _plc, ctrl, _ = _make_supervisor(cycles=cycles, rearm_holdoff_s=1.0)
    sup.step(now=0.0)
    sup.step(now=0.5)
    sup.step(now=1.2)  # past holdoff
    assert sup.mode is Mode.RUNNING
    # Bumpless arm initialized controller with current PV and MV.
    assert ctrl.reset_calls, "controller.reset should have been called on arm"
    y_arm, u_arm = ctrl.reset_calls[-1]
    assert float(y_arm[0]) == 50.0
    assert float(u_arm[0]) == 42.0


def test_running_writes_setpoint_when_not_dry_run():
    cycles = [
        make_cycle(enabled=True, hb=i + 1, mv_feedback=10.0, cv=(20.0,), setpoint_target=25.0)
        for i in range(4)
    ]
    sup, plc, _ctrl, _ = _make_supervisor(
        cycles=cycles, rearm_holdoff_s=0.5, control_period_s=0.0, dry_run=False
    )
    sup.step(now=0.0)
    sup.step(now=0.4)
    sup.step(now=1.0)  # transitions to RUNNING and immediately solves
    sup.step(now=1.5)
    tags = TagMap()
    sp_writes = [v for tag, v in plc.writes if tag == tags.mv_setpoint]
    assert sp_writes, "expected at least one MV setpoint write"


def test_dry_run_never_writes_setpoint():
    cycles = [make_cycle(enabled=True, hb=i + 1, mv_feedback=10.0, cv=(20.0,)) for i in range(5)]
    sup, plc, _ctrl, _ = _make_supervisor(
        cycles=cycles, rearm_holdoff_s=0.5, control_period_s=0.0, dry_run=True
    )
    for t in (0.0, 0.4, 1.0, 1.5, 2.0):
        sup.step(now=t)
    tags = TagMap()
    sp_writes = [v for tag, v in plc.writes if tag == tags.mv_setpoint]
    assert sp_writes == []


def test_soft_clamp_applied_to_emitted_record():
    cycles = [make_cycle(enabled=True, hb=i + 1, mv_feedback=0.0, cv=(0.0,)) for i in range(4)]
    sup, _plc, _ctrl, records = _make_supervisor(
        cycles=cycles,
        rearm_holdoff_s=0.5,
        control_period_s=0.0,
        sp_min=-0.1,
        sp_max=0.1,
        constant_move=1.0,  # controller wants u=1.0, clamp pulls to 0.1
    )
    for t in (0.0, 0.4, 1.0):
        sup.step(now=t)
    moves = [r for r in records if r["event_type"] == "control_move"]
    assert moves, "expected at least one control_move record"
    assert moves[-1]["value"] == 0.1
    assert moves[-1]["sp_raw"] == 1.0


def test_running_to_arming_on_heartbeat_loss():
    cycles = [
        make_cycle(enabled=True, hb=1, mv_feedback=0.0, cv=(0.0,)),
        make_cycle(enabled=True, hb=2, mv_feedback=0.0, cv=(0.0,)),
        make_cycle(enabled=True, hb=2, mv_feedback=0.0, cv=(0.0,)),  # frozen
    ]
    sup, *_ = _make_supervisor(cycles=cycles, rearm_holdoff_s=0.5)
    sup.step(now=0.0)
    sup.step(now=0.6)  # → RUNNING
    assert sup.mode is Mode.RUNNING
    sup.step(now=5.0)  # heartbeat hasn't advanced; timeout exceeded
    assert sup.mode is Mode.ARMING


def test_running_to_idle_when_enable_cleared():
    cycles = [
        make_cycle(enabled=True, hb=1, mv_feedback=0.0, cv=(0.0,)),
        make_cycle(enabled=True, hb=2, mv_feedback=0.0, cv=(0.0,)),
        make_cycle(enabled=False, hb=3, mv_feedback=0.0, cv=(0.0,)),
    ]
    sup, *_ = _make_supervisor(cycles=cycles, rearm_holdoff_s=0.5)
    sup.step(now=0.0)
    sup.step(now=0.6)
    assert sup.mode is Mode.RUNNING
    sup.step(now=1.0)
    assert sup.mode is Mode.IDLE


def test_io_failure_triggers_reconnect_after_cooldown():
    bad_cycles = [
        make_cycle(enabled=True, hb=1, io_ok=False) for _ in range(20)
    ]
    sup, plc, *_ = _make_supervisor(cycles=bad_cycles)
    for t in [0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0]:
        sup.step(now=t)
    assert plc.reconnect_count >= 1
