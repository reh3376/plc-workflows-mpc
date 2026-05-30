"""Plant-wide RTO runtime — periodically solve the problem and emit decisions.

Sits *above* the per-loop MPC supervisors: every ``cadence_s`` it queries the
current plant state, solves the optimization, and pushes the recommended
setpoints (one per managed loop) to the supervisor layer. Every decision is
also emitted as a record dict for governance — same shape as the supervisor's
records, with ``event_type = "optimization_decision"`` (or
``"optimization_fault"`` on failure).

Mirrors :class:`~plc_workflows_mpc.supervisor.SupervisorRunner`'s threading
model: ``run_forever`` runs sync in its own thread, ``stop()`` is signalled
via a :class:`threading.Event` so the loop exits promptly.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from plc_workflows_mpc.optimization.base import (
    LoopValues,
    OptimizationProblem,
    OptimizationResult,
    PlantOptimizer,
)

log = logging.getLogger("plc_workflows_mpc.optimization")

StateProvider = Callable[[], LoopValues]
SetpointPublisher = Callable[[LoopValues], None]
RecordSink = Callable[[dict[str, Any]], None]


@dataclass(frozen=True)
class CoordinatorConfig:
    """Identity + cadence + record-routing knobs for the coordinator."""

    cadence_s: float = 60.0
    equipment_id: str = "PLANT"
    area: str | None = None
    site: str | None = None
    operating_mode: str | None = "PRODUCTION"


@dataclass
class PlantCoordinator:
    """Periodic plant-wide optimizer.

    ``state_provider`` returns the current value of each decision variable;
    its result is used as the optimizer's initial guess so each cycle warm-
    starts from where the plant actually is. ``setpoint_publisher`` receives
    the recommended setpoints (a no-op by default — wire it to whatever pushes
    targets into the supervisors). ``record_sink`` receives one decision dict
    per solve.
    """

    problem: OptimizationProblem
    optimizer: PlantOptimizer
    config: CoordinatorConfig = field(default_factory=CoordinatorConfig)
    state_provider: StateProvider = field(default=lambda: {})
    setpoint_publisher: SetpointPublisher = field(default=lambda _setpoints: None)
    record_sink: RecordSink = field(default=lambda _record: None)

    def __post_init__(self) -> None:
        self._stop = threading.Event()
        self._next_solve = 0.0
        self._solve_count = 0
        self._last_result: OptimizationResult | None = None

    # ── Lifecycle ──────────────────────────────────────────────

    def step(self, now: float) -> None:
        """Run one decision cycle if the cadence has elapsed."""
        if now < self._next_solve:
            return
        self._next_solve = now + self.config.cadence_s
        self._solve_count += 1
        current_state = self._safe_state()
        try:
            result = self.optimizer.optimize(self.problem, initial_guess=current_state)
        except Exception as exc:  # noqa: BLE001
            log.exception("optimizer raised an exception")
            self._emit_fault(str(exc))
            return
        self._last_result = result
        if result.success:
            self._publish(result.setpoints)
            self._emit_decision(result, current_state)
        else:
            self._emit_fault(result.message or "optimizer reported failure")

    def run_forever(self) -> None:
        log.info(
            "plant coordinator start: cadence=%.1fs equipment=%s",
            self.config.cadence_s,
            self.config.equipment_id,
        )
        try:
            self._next_solve = time.monotonic()
            while not self._stop.is_set():
                self.step(time.monotonic())
                if self._stop.wait(min(self.config.cadence_s, 1.0)):
                    break
        finally:
            log.info("plant coordinator stopped (solves=%d)", self._solve_count)

    def stop(self) -> None:
        self._stop.set()

    # ── Inspection ─────────────────────────────────────────────

    @property
    def last_result(self) -> OptimizationResult | None:
        return self._last_result

    @property
    def solve_count(self) -> int:
        return self._solve_count

    # ── Helpers ────────────────────────────────────────────────

    def _safe_state(self) -> LoopValues:
        try:
            return self.state_provider() or {}
        except Exception:  # noqa: BLE001
            log.exception("state_provider raised; using initial values")
            return {}

    def _publish(self, setpoints: LoopValues) -> None:
        try:
            self.setpoint_publisher(setpoints)
        except Exception:  # noqa: BLE001
            log.exception("setpoint_publisher raised; setpoints not delivered")

    def _emit_decision(self, result: OptimizationResult, current_state: LoopValues) -> None:
        self._emit(
            self._record_base(
                event_type="optimization_decision",
                value=result.objective_value,
                extra={
                    "setpoints": dict(result.setpoints),
                    "current_state": dict(current_state),
                    "iterations": result.iterations,
                    "message": result.message,
                },
            )
        )

    def _emit_fault(self, message: str) -> None:
        self._emit(
            self._record_base(
                event_type="optimization_fault",
                value=None,
                extra={"reason": message},
            )
        )

    def _record_base(
        self,
        *,
        event_type: str,
        value: Any,
        extra: dict[str, Any],
    ) -> dict[str, Any]:
        cfg = self.config
        return {
            "equipment_id": cfg.equipment_id,
            "area": cfg.area,
            "site": cfg.site,
            "operating_mode": cfg.operating_mode,
            "loop_id": "plant",
            "controller_type": "RTO",
            "event_type": event_type,
            "value": value,
            "timestamp": datetime.now(tz=UTC).isoformat(),
            "objective_name": self.problem.objective.name,
            "objective_sense": str(self.problem.objective.sense),
            **extra,
        }

    def _emit(self, record: dict[str, Any]) -> None:
        try:
            self.record_sink(record)
        except Exception:  # noqa: BLE001
            log.exception("record_sink raised; dropping record")


__all__ = [
    "CoordinatorConfig",
    "PlantCoordinator",
    "StateProvider",
    "SetpointPublisher",
    "RecordSink",
]
