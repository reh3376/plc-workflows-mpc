"""SciPy-backed :class:`PlantOptimizer` using SLSQP for general NLPs.

SLSQP (sequential least squares programming) handles smooth nonlinear
objectives plus box bounds and inequality / equality constraints — a good
default for RTO problems with 10–100 decision variables. Linear objectives
and constraints are a degenerate (and cheap) case.

The solver works in a flat numpy vector indexed by the deterministic
``problem.variable_ids()`` order; this module wraps the user's
dict-of-loops callables so the optimizer never has to know about variable
ordering.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.optimize import minimize

from plc_workflows_mpc.optimization.base import (
    Constraint,
    LoopValues,
    ObjectiveSense,
    OptimizationProblem,
    OptimizationResult,
    PlantOptimizer,
)


@dataclass
class ScipyOptimizer(PlantOptimizer):
    """SLSQP-backed plant optimizer."""

    max_iter: int = 200
    ftol: float = 1e-7
    method: str = "SLSQP"

    def optimize(
        self,
        problem: OptimizationProblem,
        *,
        initial_guess: LoopValues | None = None,
    ) -> OptimizationResult:
        ids = problem.variable_ids()
        if not ids:
            raise ValueError("OptimizationProblem must have at least one variable")
        bounds = self._bounds(problem)
        x0 = self._initial_x(problem, initial_guess)
        sign = -1.0 if problem.objective.sense is ObjectiveSense.MAXIMIZE else 1.0

        def objective(x: np.ndarray) -> float:
            return sign * problem.objective.function(_x_to_dict(x, ids))

        scipy_constraints = [
            _constraint_to_scipy(c, ids) for c in problem.constraints
        ]

        result = minimize(
            objective,
            x0,
            method=self.method,
            bounds=bounds,
            constraints=scipy_constraints,
            options={"maxiter": self.max_iter, "ftol": self.ftol},
        )

        setpoints = _x_to_dict(result.x, ids) if result.success else {}
        return OptimizationResult(
            setpoints=setpoints,
            objective_value=float(problem.objective.function(setpoints) if result.success else 0.0),
            iterations=int(getattr(result, "nit", 0)),
            success=bool(result.success),
            message=str(result.message),
        )

    # ── helpers ───────────────────────────────────────────────

    @staticmethod
    def _bounds(problem: OptimizationProblem) -> list[tuple[float | None, float | None]]:
        return [(v.lower_bound, v.upper_bound) for v in problem.variables]

    @staticmethod
    def _initial_x(
        problem: OptimizationProblem,
        initial_guess: LoopValues | None,
    ) -> np.ndarray:
        guess = initial_guess or {}
        return np.array(
            [float(guess.get(v.loop_id, v.initial_value)) for v in problem.variables],
            dtype=float,
        )


def _x_to_dict(x: np.ndarray, ids: tuple[str, ...]) -> LoopValues:
    return {loop_id: float(value) for loop_id, value in zip(ids, x, strict=True)}


def _constraint_to_scipy(constraint: Constraint, ids: tuple[str, ...]) -> dict[str, Any]:
    """Translate a Constraint into SciPy's ``{type, fun}`` form."""
    bound = constraint.bound
    fn = constraint.function

    if constraint.sense == "==":
        return {"type": "eq", "fun": lambda x: fn(_x_to_dict(x, ids)) - bound}
    if constraint.sense == ">=":
        return {"type": "ineq", "fun": lambda x: fn(_x_to_dict(x, ids)) - bound}
    # "<="  ⇒ bound − fn ≥ 0
    return {"type": "ineq", "fun": lambda x: bound - fn(_x_to_dict(x, ids))}


__all__ = ["ScipyOptimizer"]
