"""Pillar 4 — Plant-wide system optimization.

The top layer: coordinate all individual MPC controllers toward a user-defined
plant objective (e.g. *"maximize proof gallons produced"*) subject to process
and business constraints. This real-time optimization (RTO) layer sits above
the MPC controllers and adjusts their setpoints on a slow cadence (typically
seconds to minutes) while the MPCs track those setpoints on a fast cadence.

Phase 4 ships:

* the public types — :class:`LoopVariable`, :class:`Constraint`,
  :class:`PlantObjective`, :class:`OptimizationProblem`,
  :class:`OptimizationResult`, and the :class:`PlantOptimizer` ABC
  (see :mod:`plc_workflows_mpc.optimization.base`);
* a concrete :class:`ScipyOptimizer` backed by SLSQP — handles smooth
  nonlinear objectives and constraints out of the box (see
  :mod:`plc_workflows_mpc.optimization.scipy_backend`);
* a :class:`PlantCoordinator` runtime that periodically solves the problem
  and emits decision records, mirroring the supervisor's threading model
  (see :mod:`plc_workflows_mpc.optimization.coordinator`).

Wire :class:`PlantCoordinator`'s ``setpoint_publisher`` to whatever pushes
targets into your supervisors, and its ``record_sink`` to the spoke's
``queue_record`` so every plant-wide decision becomes a governed
``ContextualRecord``.
"""

from __future__ import annotations

from plc_workflows_mpc.optimization.base import (
    Constraint,
    ConstraintFunction,
    ConstraintSense,
    LoopValues,
    LoopVariable,
    ObjectiveFunction,
    ObjectiveSense,
    OptimizationProblem,
    OptimizationResult,
    PlantObjective,
    PlantOptimizer,
)
from plc_workflows_mpc.optimization.coordinator import (
    CoordinatorConfig,
    PlantCoordinator,
    RecordSink,
    SetpointPublisher,
    StateProvider,
)
from plc_workflows_mpc.optimization.scipy_backend import ScipyOptimizer


def build_optimizer(objective: PlantObjective | None = None, **_kwargs: object) -> PlantOptimizer:
    """Return a sensible default :class:`PlantOptimizer` (``ScipyOptimizer``).

    ``objective`` is accepted for compatibility with earlier signatures but is
    not used to pick a backend — the SLSQP backend handles both linear and
    nonlinear objectives. Pass solver knobs via keyword arguments if desired.
    """
    return ScipyOptimizer(**_kwargs)  # type: ignore[arg-type]


__all__ = [
    "ObjectiveSense",
    "ConstraintSense",
    "LoopValues",
    "ObjectiveFunction",
    "ConstraintFunction",
    "LoopVariable",
    "Constraint",
    "PlantObjective",
    "OptimizationProblem",
    "OptimizationResult",
    "PlantOptimizer",
    "ScipyOptimizer",
    "CoordinatorConfig",
    "PlantCoordinator",
    "StateProvider",
    "SetpointPublisher",
    "RecordSink",
    "build_optimizer",
]
