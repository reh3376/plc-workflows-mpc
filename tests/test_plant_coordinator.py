"""Tests for the PlantCoordinator runtime."""

from __future__ import annotations

import threading
import time

import pytest

from plc_workflows_mpc.optimization import (
    Constraint,
    CoordinatorConfig,
    LoopVariable,
    ObjectiveSense,
    OptimizationProblem,
    PlantCoordinator,
    PlantObjective,
    ScipyOptimizer,
)


def _proof_gallons_problem() -> OptimizationProblem:
    return OptimizationProblem(
        objective=PlantObjective(
            name="proof_gallons",
            sense=ObjectiveSense.MAXIMIZE,
            function=lambda v: 0.6 * v["a"] + 0.5 * v["b"],
            description="Plant-wide throughput",
        ),
        variables=(
            LoopVariable("a", lower_bound=0.0, upper_bound=100.0),
            LoopVariable("b", lower_bound=0.0, upper_bound=80.0),
        ),
        constraints=(Constraint("steam", lambda v: v["a"] + v["b"], "<=", 150.0),),
    )


def test_step_runs_optimization_and_emits_decision():
    problem = _proof_gallons_problem()
    published: list[dict[str, float]] = []
    records: list[dict] = []
    coord = PlantCoordinator(
        problem=problem,
        optimizer=ScipyOptimizer(),
        config=CoordinatorConfig(cadence_s=5.0, equipment_id="PLANT-1"),
        state_provider=lambda: {"a": 50.0, "b": 50.0},
        setpoint_publisher=published.append,
        record_sink=records.append,
    )
    coord.step(now=0.0)
    assert published, "setpoint_publisher should have received recommended setpoints"
    decisions = [r for r in records if r["event_type"] == "optimization_decision"]
    assert decisions, "a decision record should have been emitted"
    decision = decisions[0]
    assert decision["controller_type"] == "RTO"
    assert decision["objective_name"] == "proof_gallons"
    assert decision["equipment_id"] == "PLANT-1"
    assert set(decision["setpoints"].keys()) == {"a", "b"}
    assert coord.last_result is not None and coord.last_result.success


def test_step_respects_cadence():
    coord = PlantCoordinator(
        problem=_proof_gallons_problem(),
        optimizer=ScipyOptimizer(),
        config=CoordinatorConfig(cadence_s=10.0),
        state_provider=lambda: {"a": 0.0, "b": 0.0},
    )
    coord.step(now=0.0)
    first = coord.solve_count
    coord.step(now=5.0)  # before cadence elapses
    assert coord.solve_count == first
    coord.step(now=15.0)  # past cadence
    assert coord.solve_count == first + 1


def test_optimizer_failure_emits_fault_record():
    records: list[dict] = []

    class _BoomOptimizer(ScipyOptimizer):
        def optimize(self, problem, *, initial_guess=None):  # type: ignore[override]
            raise RuntimeError("boom")

    coord = PlantCoordinator(
        problem=_proof_gallons_problem(),
        optimizer=_BoomOptimizer(),
        record_sink=records.append,
    )
    coord.step(now=0.0)
    faults = [r for r in records if r["event_type"] == "optimization_fault"]
    assert len(faults) == 1
    assert "boom" in faults[0]["reason"]


def test_state_provider_failure_uses_initial_values():
    """If state_provider raises, the coordinator still runs and emits."""
    records: list[dict] = []

    def _bad_state() -> dict[str, float]:
        raise RuntimeError("nope")

    coord = PlantCoordinator(
        problem=_proof_gallons_problem(),
        optimizer=ScipyOptimizer(),
        state_provider=_bad_state,
        record_sink=records.append,
    )
    coord.step(now=0.0)
    assert any(r["event_type"] == "optimization_decision" for r in records)


def test_record_sink_errors_do_not_kill_step():
    def _angry_sink(_record: dict) -> None:
        raise RuntimeError("don't like it")

    coord = PlantCoordinator(
        problem=_proof_gallons_problem(),
        optimizer=ScipyOptimizer(),
        state_provider=lambda: {"a": 0.0, "b": 0.0},
        record_sink=_angry_sink,
    )
    # Must not raise.
    coord.step(now=0.0)
    assert coord.solve_count == 1


def test_run_forever_in_thread_then_stop():
    records: list[dict] = []
    coord = PlantCoordinator(
        problem=_proof_gallons_problem(),
        optimizer=ScipyOptimizer(),
        config=CoordinatorConfig(cadence_s=0.05),
        state_provider=lambda: {"a": 0.0, "b": 0.0},
        record_sink=records.append,
    )
    thread = threading.Thread(target=coord.run_forever, daemon=True)
    thread.start()
    deadline = time.monotonic() + 1.5
    while coord.solve_count < 2 and time.monotonic() < deadline:
        time.sleep(0.05)
    coord.stop()
    thread.join(timeout=2.0)
    assert not thread.is_alive()
    assert coord.solve_count >= 2
    assert records, "run_forever should produce records"


def test_setpoint_publisher_errors_do_not_kill_step():
    def _bad_publisher(_setpoints):
        raise RuntimeError("publish failed")

    records: list[dict] = []
    coord = PlantCoordinator(
        problem=_proof_gallons_problem(),
        optimizer=ScipyOptimizer(),
        state_provider=lambda: {"a": 0.0, "b": 0.0},
        setpoint_publisher=_bad_publisher,
        record_sink=records.append,
    )
    coord.step(now=0.0)
    assert any(r["event_type"] == "optimization_decision" for r in records)


@pytest.mark.parametrize(
    ("sense", "expected"),
    [
        (ObjectiveSense.MAXIMIZE, "maximize"),
        (ObjectiveSense.MINIMIZE, "minimize"),
    ],
)
def test_sense_propagates_into_records(sense, expected):
    problem = OptimizationProblem(
        objective=PlantObjective(name="x", sense=sense, function=lambda v: v["a"]),
        variables=(LoopVariable("a", lower_bound=0.0, upper_bound=10.0),),
    )
    records: list[dict] = []
    PlantCoordinator(
        problem=problem,
        optimizer=ScipyOptimizer(),
        record_sink=records.append,
    ).step(now=0.0)
    decision = next(r for r in records if r["event_type"] == "optimization_decision")
    assert decision["objective_sense"] == expected
