"""Tests for control-strategy selection heuristics."""

from __future__ import annotations

import pytest

from plc_workflows_mpc.apc.identification import ProcessModel
from plc_workflows_mpc.apc.selection import (
    ControlStrategy,
    recommend_strategy,
    recommend_strategy_with_rationale,
)


def _fopdt(*, gain: float = 1.0, tau: float = 10.0, theta: float = 1.0) -> ProcessModel:
    return ProcessModel(
        model_type="FOPDT",
        parameters={"gain": gain, "time_constant": tau, "dead_time": theta},
        fit_quality=1.0,
    )


def _sopdt(
    *, gain: float = 1.0, tau1: float = 10.0, tau2: float = 4.0, theta: float = 1.0
) -> ProcessModel:
    return ProcessModel(
        model_type="SOPDT",
        parameters={"gain": gain, "tau1": tau1, "tau2": tau2, "dead_time": theta},
        fit_quality=1.0,
    )


@pytest.mark.parametrize(
    ("theta", "tau", "expected"),
    [
        (0.5, 20.0, ControlStrategy.PID),  # θ/τ = 0.025
        (3.0, 10.0, ControlStrategy.APC),  # θ/τ = 0.30
        (15.0, 10.0, ControlStrategy.MPC),  # θ/τ = 1.50
    ],
)
def test_dead_time_ratio_branches(theta, tau, expected):
    model = _fopdt(theta=theta, tau=tau)
    assert recommend_strategy(model) == expected


def test_mimo_always_picks_mpc():
    model = _fopdt(theta=0.1, tau=20.0)  # would be PID otherwise
    assert recommend_strategy(model, mimo=True) == ControlStrategy.MPC


def test_hard_constraints_pick_mpc():
    model = _fopdt(theta=0.1, tau=20.0)
    assert recommend_strategy(model, has_hard_constraints=True) == ControlStrategy.MPC


def test_measured_disturbance_picks_mpc():
    model = _fopdt(theta=0.1, tau=20.0)
    assert recommend_strategy(model, has_measured_disturbance=True) == ControlStrategy.MPC


def test_sopdt_uses_dominant_time_constant():
    # τ_dom = 12, θ = 3 → θ/τ = 0.25 → APC
    model = _sopdt(tau1=12.0, tau2=4.0, theta=3.0)
    assert recommend_strategy(model) == ControlStrategy.APC


def test_missing_dead_time_falls_back_to_pid():
    model = ProcessModel(model_type="FOPDT", parameters={"gain": 1.0, "time_constant": 5.0})
    rationale = recommend_strategy_with_rationale(model)
    assert rationale.strategy == ControlStrategy.PID
    assert rationale.dead_time_ratio is None
    assert "defaulting to PID" in rationale.reason


def test_rationale_includes_ratio_and_reason():
    model = _fopdt(theta=3.0, tau=10.0)
    rationale = recommend_strategy_with_rationale(model)
    assert rationale.strategy == ControlStrategy.APC
    assert rationale.dead_time_ratio == pytest.approx(0.3, abs=1e-6)
    assert "θ/τ" in rationale.reason


def test_custom_thresholds_change_recommendation():
    model = _fopdt(theta=0.3, tau=10.0)  # ratio = 0.03
    # Default: PID (< 0.2). With apc_threshold=0.01, becomes APC.
    assert recommend_strategy(model) == ControlStrategy.PID
    assert recommend_strategy(model, apc_threshold=0.01) == ControlStrategy.APC
