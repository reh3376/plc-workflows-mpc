"""Tests for the OSQP-backed LinearMpcController."""

from __future__ import annotations

import numpy as np
import pytest

from plc_workflows_mpc.apc.identification import ProcessModel
from plc_workflows_mpc.apc.mpc import (
    MpcConfig,
    PlantModel,
    instantiate_mpc,
    plant_model_from_identified,
)


def _fopdt_plant(*, k: float = 2.0, tau: float = 5.0, ts: float = 1.0) -> PlantModel:
    model = ProcessModel(
        model_type="FOPDT",
        parameters={"gain": k, "time_constant": tau, "dead_time": 0.0},
    )
    return plant_model_from_identified(model, ts=ts)


def _closed_loop(
    plant: PlantModel,
    controller,
    *,
    setpoint: float,
    n: int,
    load: float = 0.0,
    initial_mv: float = 0.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Run a closed-loop simulation, returning y_meas and u sequences."""
    x = np.zeros(plant.A.shape[0])
    ys = np.zeros(n)
    us = np.zeros(n)
    controller.reset(y_meas=np.array([0.0]), u_active=np.array([initial_mv]))
    sp_vec = np.array([setpoint])
    no_dv = np.zeros(0)
    for i in range(n):
        y_true = float((plant.C @ x)[0])
        y_meas = y_true + load
        ys[i] = y_meas
        controller.estimate(np.array([y_meas]), no_dv)
        u = controller.solve(sp_vec, no_dv)
        controller.commit(u)
        us[i] = float(u[0])
        x = plant.A @ x + plant.Bu @ u
    return ys, us


def test_controller_tracks_setpoint():
    plant = _fopdt_plant(k=2.0, tau=5.0, ts=1.0)
    cfg = MpcConfig(prediction_horizon=20, control_horizon=5)
    ctrl = instantiate_mpc(plant, cfg)
    y, _ = _closed_loop(plant, ctrl, setpoint=5.0, n=60)
    assert y[-1] == pytest.approx(5.0, abs=0.1)


def test_controller_respects_mv_upper_bound():
    plant = _fopdt_plant(k=2.0, tau=5.0, ts=1.0)
    cfg = MpcConfig(
        prediction_horizon=20,
        control_horizon=5,
        u_min=(-0.5,),
        u_max=(0.5,),
        du_max=(2.0,),
    )
    ctrl = instantiate_mpc(plant, cfg)
    _, u = _closed_loop(plant, ctrl, setpoint=100.0, n=40)  # setpoint forces saturation
    # OSQP tolerance: allow a tiny numerical slack.
    assert u.max() <= 0.5 + 1e-3
    assert u.min() >= -0.5 - 1e-3


def test_controller_respects_rate_limit():
    plant = _fopdt_plant(k=2.0, tau=5.0, ts=1.0)
    cfg = MpcConfig(
        prediction_horizon=20,
        control_horizon=5,
        du_max=(0.1,),
    )
    ctrl = instantiate_mpc(plant, cfg)
    _, u = _closed_loop(plant, ctrl, setpoint=10.0, n=30)
    du = np.diff(np.concatenate([[0.0], u]))
    assert np.max(np.abs(du)) <= 0.1 + 1e-3


def test_offset_free_observer_rejects_unmeasured_load():
    plant = _fopdt_plant(k=2.0, tau=5.0, ts=1.0)
    cfg = MpcConfig(
        prediction_horizon=20,
        control_horizon=5,
        q_kf_dist=1.0,  # aggressive disturbance rejection
    )
    ctrl = instantiate_mpc(plant, cfg)
    # Unmeasured constant load shifts y_meas by +2.0.
    y, _ = _closed_loop(plant, ctrl, setpoint=5.0, n=200, load=2.0)
    assert y[-1] == pytest.approx(5.0, abs=0.05)


def test_feedforward_anticipates_measured_disturbance():
    """With Bd non-zero and d_meas fed to solve(), the controller pre-acts."""
    # Build a plant by hand: y(k+1) = 0.8 y(k) + 0.4 u(k) + 0.3 d(k)
    plant = PlantModel(
        A=np.array([[0.8]]),
        Bu=np.array([[0.4]]),
        Bd=np.array([[0.3]]),
        C=np.array([[1.0]]),
        ts=1.0,
    )
    cfg = MpcConfig(prediction_horizon=20, control_horizon=5)
    ctrl = instantiate_mpc(plant, cfg)

    ctrl.reset(y_meas=np.array([0.0]), u_active=np.array([0.0]))
    sp = np.array([0.0])
    d = np.array([1.0])  # measured disturbance steps up
    # First solve with feedforward — controller should choose u that opposes d.
    ctrl.estimate(np.array([0.0]), d)
    u_with_ff = ctrl.solve(sp, d)
    # The optimal move negates Bd·d / Bu: u ≈ -0.75
    assert u_with_ff[0] < -0.5


def test_infeasible_solve_holds_last_input():
    """If the QP fails (or returns invalid status), controller returns u_prev."""
    plant = _fopdt_plant()
    cfg = MpcConfig(prediction_horizon=10, control_horizon=3)
    ctrl = instantiate_mpc(plant, cfg)
    ctrl.reset(y_meas=np.array([0.0]), u_active=np.array([0.7]))

    class _FailingProb:
        def update(self, **_kwargs):
            return None

        def solve(self):
            class _R:
                class info:
                    status_val = -3  # primal infeasible

                x = np.zeros(3)

            return _R()

    ctrl._prob = _FailingProb()  # type: ignore[attr-defined]
    out = ctrl.solve(np.array([5.0]), np.zeros(0))
    assert out[0] == pytest.approx(0.7)


def test_config_validation_rejects_mismatched_lengths():
    plant = _fopdt_plant()
    bad = MpcConfig(prediction_horizon=10, control_horizon=3, q=(1.0, 2.0))  # ny=1, length=2
    with pytest.raises(ValueError):
        instantiate_mpc(plant, bad)


def test_config_validation_rejects_inverted_horizons():
    plant = _fopdt_plant()
    with pytest.raises(ValueError):
        instantiate_mpc(plant, MpcConfig(prediction_horizon=2, control_horizon=5))
