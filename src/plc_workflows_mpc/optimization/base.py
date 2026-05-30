"""Public types for the plant-wide real-time optimization (RTO) package.

A plant-wide RTO problem has three parts:

* a **plant objective** the customer wants to drive (e.g. *maximize proof
  gallons produced*) expressed as a callable over the decision variables;
* a set of **decision variables** — typically one per control loop, naming
  the loop and its allowable range; the optimizer recommends a new setpoint
  for each;
* zero or more **constraints** — bounds, capacity limits, mass-balance or
  business rules — expressed as callables on the decision-variable dict.

The optimizer maps a current plant state (today's variable values) to a new
recommended setpoint dict; the supervisor below it then tracks those
setpoints with its MPC controller.
"""

from __future__ import annotations

import abc
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal

ConstraintSense = Literal["<=", ">=", "=="]
LoopValues = dict[str, float]
ObjectiveFunction = Callable[[LoopValues], float]
ConstraintFunction = Callable[[LoopValues], float]


class ObjectiveSense(StrEnum):
    """Whether the plant objective is maximized or minimized."""

    MAXIMIZE = "maximize"
    MINIMIZE = "minimize"


@dataclass(frozen=True)
class LoopVariable:
    """A decision variable the optimizer controls — typically a loop setpoint.

    ``loop_id`` is the key into the variable dict the objective and constraints
    receive. ``lower_bound`` / ``upper_bound`` may be ``None`` for unbounded.
    ``initial_value`` seeds the solver if no explicit guess is supplied.
    """

    loop_id: str
    name: str = ""
    lower_bound: float | None = None
    upper_bound: float | None = None
    initial_value: float = 0.0
    engineering_units: str = ""


@dataclass(frozen=True)
class Constraint:
    """A plant constraint expressed as ``function(x) sense bound``.

    Examples::

        Constraint("total_steam", lambda v: v["loop_a"] + v["loop_b"], "<=", 100.0)
        Constraint("quality_min", quality_model, ">=", 95.0)
        Constraint("mass_balance", mass_residual, "==", 0.0)
    """

    name: str
    function: ConstraintFunction
    sense: ConstraintSense
    bound: float = 0.0


@dataclass(frozen=True)
class PlantObjective:
    """The user-defined plant objective.

    ``function`` maps a dict of loop values to a scalar objective value.
    ``sense`` decides whether the optimizer maximizes or minimizes. ``name``
    and ``description`` are surfaced in emitted decision records.
    """

    name: str
    sense: ObjectiveSense
    function: ObjectiveFunction
    description: str = ""


@dataclass(frozen=True)
class OptimizationProblem:
    """A fully-specified RTO problem ready to be solved."""

    objective: PlantObjective
    variables: tuple[LoopVariable, ...]
    constraints: tuple[Constraint, ...] = ()

    def variable_ids(self) -> tuple[str, ...]:
        return tuple(v.loop_id for v in self.variables)


@dataclass(frozen=True)
class OptimizationResult:
    """Outcome of one RTO solve.

    ``setpoints`` is empty when ``success`` is False; ``objective_value`` is
    the value of the objective at ``setpoints`` (the maximization sign has been
    *applied*, so larger is better when the problem was maximization).
    """

    setpoints: LoopValues = field(default_factory=dict)
    objective_value: float = 0.0
    iterations: int = 0
    success: bool = False
    message: str = ""


class PlantOptimizer(abc.ABC):
    """Solves an :class:`OptimizationProblem` and returns recommended setpoints."""

    @abc.abstractmethod
    def optimize(
        self,
        problem: OptimizationProblem,
        *,
        initial_guess: LoopValues | None = None,
    ) -> OptimizationResult:
        """Recommend setpoints; ``initial_guess`` overrides each variable's seed."""


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
]
