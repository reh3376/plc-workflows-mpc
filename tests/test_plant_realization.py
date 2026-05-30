"""Tests for FOPDT / SOPDT → state-space realization."""

from __future__ import annotations

import numpy as np
import pytest

from plc_workflows_mpc.apc.identification import ProcessModel
from plc_workflows_mpc.apc.mpc import PlantModel, plant_model_from_identified


def _simulate_step(plant: PlantModel, n: int, u: float = 1.0) -> np.ndarray:
    """Drive the plant with a constant step input ``u`` from x=0, return y[k]."""
    x = np.zeros(plant.A.shape[0])
    u_vec = np.array([u])
    ys = np.zeros(n)
    for k in range(n):
        ys[k] = float((plant.C @ x)[0])
        x = plant.A @ x + plant.Bu @ u_vec
    return ys


# ── FOPDT realization ------------------------------------------------------


def test_fopdt_no_dead_time_steady_state_equals_gain():
    model = ProcessModel(
        model_type="FOPDT",
        parameters={"gain": 2.0, "time_constant": 5.0, "dead_time": 0.0},
    )
    plant = plant_model_from_identified(model, ts=0.5)
    assert plant.A.shape == (1, 1)
    assert plant.Bu.shape == (1, 1)
    assert plant.C.shape == (1, 1)
    assert plant.Bd.shape == (1, 0)

    y = _simulate_step(plant, n=120, u=1.0)
    # After 5τ samples (~50 samples here) the response should be very close to K.
    assert y[-1] == pytest.approx(2.0, rel=1e-3)


def test_fopdt_dead_time_adds_delay_buffer():
    ts = 1.0
    model = ProcessModel(
        model_type="FOPDT",
        parameters={"gain": 1.0, "time_constant": 5.0, "dead_time": 3.0},
    )
    plant = plant_model_from_identified(model, ts=ts)
    # 1 dynamic state + 3 delay states
    assert plant.A.shape == (4, 4)

    y = _simulate_step(plant, n=40, u=1.0)
    # For the first n_d samples after applying the input, y must stay at 0.
    assert np.allclose(y[:3], 0.0)
    # By 5 time constants past the dead time the response should be near 1.
    assert y[-1] == pytest.approx(1.0, abs=0.05)


def test_fopdt_rejects_invalid_params():
    bad = ProcessModel(
        model_type="FOPDT", parameters={"gain": 1.0, "time_constant": 0.0, "dead_time": 0.0}
    )
    with pytest.raises(ValueError):
        plant_model_from_identified(bad, ts=0.5)


# ── SOPDT realization ------------------------------------------------------


def test_sopdt_steady_state_equals_gain():
    model = ProcessModel(
        model_type="SOPDT",
        parameters={"gain": 1.5, "tau1": 10.0, "tau2": 2.0, "dead_time": 0.0},
    )
    plant = plant_model_from_identified(model, ts=0.5)
    # 2 dynamic states + 0 delay states
    assert plant.A.shape == (2, 2)

    y = _simulate_step(plant, n=200, u=1.0)
    assert y[-1] == pytest.approx(1.5, rel=1e-3)


def test_sopdt_dead_time_adds_delay_buffer():
    ts = 1.0
    model = ProcessModel(
        model_type="SOPDT",
        parameters={"gain": 1.0, "tau1": 6.0, "tau2": 2.0, "dead_time": 4.0},
    )
    plant = plant_model_from_identified(model, ts=ts)
    # 2 dynamic + 4 delay
    assert plant.A.shape == (6, 6)
    y = _simulate_step(plant, n=60, u=1.0)
    assert np.allclose(y[:4], 0.0)
    assert y[-1] == pytest.approx(1.0, abs=0.05)


# ── Errors ------------------------------------------------------------------


def test_unsupported_model_type_raises():
    model = ProcessModel(
        model_type="state_space", parameters={"gain": 1.0, "time_constant": 1.0}
    )
    with pytest.raises(NotImplementedError):
        plant_model_from_identified(model, ts=0.5)


def test_nonpositive_ts_rejected():
    model = ProcessModel(
        model_type="FOPDT",
        parameters={"gain": 1.0, "time_constant": 5.0, "dead_time": 0.0},
    )
    with pytest.raises(ValueError):
        plant_model_from_identified(model, ts=0.0)
