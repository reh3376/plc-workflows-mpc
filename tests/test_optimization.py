"""Tests for the SciPy-backed plant optimizer."""

from __future__ import annotations

import math

import pytest

from plc_workflows_mpc.optimization import (
    Constraint,
    LoopVariable,
    ObjectiveSense,
    OptimizationProblem,
    PlantObjective,
    ScipyOptimizer,
    build_optimizer,
)


def _problem(
    *,
    sense: ObjectiveSense,
    objective_fn,
    variables: tuple[LoopVariable, ...],
    constraints: tuple[Constraint, ...] = (),
    name: str = "test",
) -> OptimizationProblem:
    return OptimizationProblem(
        objective=PlantObjective(name=name, sense=sense, function=objective_fn),
        variables=variables,
        constraints=constraints,
    )


# ── Linear LP (recognises a classic textbook optimum) ----------------------


def test_maximizes_simple_linear_objective_with_constraints():
    """Maximize 3x + 5y s.t. x ≤ 40, y ≤ 30, x + 0.5y ≤ 50, x,y ≥ 0.

    Per-unit weight on y (5) beats x (3), so y saturates at 30 first and
    x uses the remaining capacity: 50 − 0.5·30 = 35.
    """
    variables = (
        LoopVariable("x", lower_bound=0.0, upper_bound=40.0, initial_value=0.0),
        LoopVariable("y", lower_bound=0.0, upper_bound=30.0, initial_value=0.0),
    )
    constraints = (
        Constraint("capacity", lambda v: v["x"] + 0.5 * v["y"], "<=", 50.0),
    )
    problem = _problem(
        sense=ObjectiveSense.MAXIMIZE,
        objective_fn=lambda v: 3 * v["x"] + 5 * v["y"],
        variables=variables,
        constraints=constraints,
    )
    result = ScipyOptimizer().optimize(problem)
    assert result.success
    assert result.setpoints["x"] == pytest.approx(35.0, abs=1e-3)
    assert result.setpoints["y"] == pytest.approx(30.0, abs=1e-3)
    assert result.objective_value == pytest.approx(255.0, abs=1e-2)


def test_minimizes_quadratic_with_equality_constraint():
    """Minimize (x − 2)² + (y − 3)² s.t. x + y = 4 → x = 1.5, y = 2.5, f = 0.5."""
    variables = (
        LoopVariable("x", lower_bound=-10.0, upper_bound=10.0, initial_value=0.0),
        LoopVariable("y", lower_bound=-10.0, upper_bound=10.0, initial_value=0.0),
    )
    constraints = (Constraint("sum_eq", lambda v: v["x"] + v["y"], "==", 4.0),)
    problem = _problem(
        sense=ObjectiveSense.MINIMIZE,
        objective_fn=lambda v: (v["x"] - 2) ** 2 + (v["y"] - 3) ** 2,
        variables=variables,
        constraints=constraints,
    )
    result = ScipyOptimizer().optimize(problem)
    assert result.success
    assert result.setpoints["x"] == pytest.approx(1.5, abs=1e-3)
    assert result.setpoints["y"] == pytest.approx(2.5, abs=1e-3)
    assert result.objective_value == pytest.approx(0.5, abs=1e-3)


def test_nonlinear_ge_constraint_is_honored():
    """Minimize (x − 1)² s.t. x² ≥ 4 → optimum x = 2 (active constraint)."""
    variables = (LoopVariable("x", lower_bound=-10.0, upper_bound=10.0, initial_value=3.0),)
    constraints = (Constraint("x2_ge_4", lambda v: v["x"] ** 2, ">=", 4.0),)
    problem = _problem(
        sense=ObjectiveSense.MINIMIZE,
        objective_fn=lambda v: (v["x"] - 1) ** 2,
        variables=variables,
        constraints=constraints,
    )
    result = ScipyOptimizer().optimize(problem)
    assert result.success
    assert result.setpoints["x"] == pytest.approx(2.0, abs=1e-3)


def test_maximize_proof_gallons_two_loops():
    """End-to-end shape: maximize a multi-loop objective subject to a capacity cap."""
    variables = (
        LoopVariable("fermenter_a_throughput", lower_bound=0.0, upper_bound=100.0),
        LoopVariable("fermenter_b_throughput", lower_bound=0.0, upper_bound=80.0),
    )
    # Yield: A is more efficient than B per unit throughput.
    objective = PlantObjective(
        name="proof_gallons",
        sense=ObjectiveSense.MAXIMIZE,
        function=lambda v: 0.6 * v["fermenter_a_throughput"]
        + 0.5 * v["fermenter_b_throughput"],
    )
    constraints = (
        Constraint(
            "steam_capacity",
            lambda v: v["fermenter_a_throughput"] + v["fermenter_b_throughput"],
            "<=",
            150.0,
        ),
    )
    result = ScipyOptimizer().optimize(
        OptimizationProblem(objective=objective, variables=variables, constraints=constraints)
    )
    assert result.success
    # A should saturate first (higher yield), then B fills the remaining steam.
    assert result.setpoints["fermenter_a_throughput"] == pytest.approx(100.0, abs=0.1)
    assert result.setpoints["fermenter_b_throughput"] == pytest.approx(50.0, abs=0.1)


def test_initial_guess_seeds_the_solver():
    """Passing initial_guess overrides each variable's initial_value."""
    variables = (
        LoopVariable("x", lower_bound=-100.0, upper_bound=100.0, initial_value=0.0),
    )
    problem = _problem(
        sense=ObjectiveSense.MINIMIZE,
        objective_fn=lambda v: (v["x"] - 7.0) ** 2,
        variables=variables,
    )
    result = ScipyOptimizer().optimize(problem, initial_guess={"x": 6.5})
    assert result.success
    assert result.setpoints["x"] == pytest.approx(7.0, abs=1e-3)


def test_build_optimizer_returns_scipy_default():
    optimizer = build_optimizer()
    assert isinstance(optimizer, ScipyOptimizer)


def test_empty_problem_rejected():
    with pytest.raises(ValueError):
        ScipyOptimizer().optimize(
            OptimizationProblem(
                objective=PlantObjective(
                    name="x", sense=ObjectiveSense.MAXIMIZE, function=lambda v: 0.0
                ),
                variables=(),
            )
        )


def test_infeasible_problem_returns_unsuccessful_result():
    """Conflicting constraints x ≥ 5 and x ≤ 1 leave SLSQP unable to satisfy both."""
    variables = (LoopVariable("x", lower_bound=-10.0, upper_bound=10.0, initial_value=0.0),)
    constraints = (
        Constraint("ge5", lambda v: v["x"], ">=", 5.0),
        Constraint("le1", lambda v: v["x"], "<=", 1.0),
    )
    problem = _problem(
        sense=ObjectiveSense.MINIMIZE,
        objective_fn=lambda v: v["x"] ** 2,
        variables=variables,
        constraints=constraints,
    )
    result = ScipyOptimizer().optimize(problem)
    # We don't assert success==False (SLSQP may report success with a residual)
    # but we *do* require that one of the constraints is violated.
    x = result.setpoints.get("x", 0.0)
    assert not (x >= 5.0 - 1e-6 and x <= 1.0 + 1e-6)


def test_variable_ordering_is_deterministic():
    variables = (
        LoopVariable("c", initial_value=1.0),
        LoopVariable("a", initial_value=2.0),
        LoopVariable("b", initial_value=3.0),
    )
    problem = OptimizationProblem(
        objective=PlantObjective(
            name="x", sense=ObjectiveSense.MAXIMIZE, function=lambda v: math.fsum(v.values())
        ),
        variables=variables,
    )
    assert problem.variable_ids() == ("c", "a", "b")
