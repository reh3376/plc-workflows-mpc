"""Tests for FOPDT/SOPDT identification and step detection."""

from __future__ import annotations

import numpy as np
import pytest

from plc_workflows_mpc.apc.identification import (
    LeastSquaresIdentifier,
    StepTest,
    detect_steps,
    fit_fopdt,
    fit_sopdt,
    fopdt_step_response,
    identify_process_model,
    sopdt_step_response,
)


def _make_fopdt_steptest(
    *,
    k: float = 2.0,
    tau: float = 10.0,
    theta: float = 2.0,
    pre: float = 10.0,
    dt: float = 0.5,
    total: float = 100.0,
    noise: float = 0.0,
    seed: int = 0,
) -> tuple[StepTest, dict[str, float]]:
    rng = np.random.default_rng(seed)
    t = np.arange(0.0, total, dt)
    u = np.where(t >= pre, 1.0, 0.0)
    y = np.zeros_like(t)
    mask = t >= pre + theta
    y[mask] = k * (1.0 - np.exp(-(t[mask] - pre - theta) / tau))
    if noise:
        y = y + rng.normal(0.0, noise, size=y.shape)
    return StepTest(t=t, u=u, y=y), {"k": k, "tau": tau, "theta": theta, "pre": pre}


def _make_sopdt_steptest(
    *,
    k: float = 1.5,
    tau1: float = 12.0,
    tau2: float = 4.0,
    theta: float = 1.0,
    pre: float = 20.0,
    dt: float = 0.5,
    total: float = 200.0,
    noise: float = 0.0,
    seed: int = 1,
) -> tuple[StepTest, dict[str, float]]:
    rng = np.random.default_rng(seed)
    t = np.arange(0.0, total, dt)
    u = np.where(t >= pre, 1.0, 0.0)
    tt = t - pre - theta
    y = np.where(
        t >= pre + theta,
        k * (1.0 - (tau1 * np.exp(-tt / tau1) - tau2 * np.exp(-tt / tau2)) / (tau1 - tau2)),
        0.0,
    )
    if noise:
        y = y + rng.normal(0.0, noise, size=y.shape)
    return StepTest(t=t, u=u, y=y), {
        "k": k,
        "tau1": tau1,
        "tau2": tau2,
        "theta": theta,
        "pre": pre,
    }


# ── Step response shape -----------------------------------------------------


def test_fopdt_response_reaches_steady_state():
    t = np.linspace(0.0, 100.0, 201)
    y = fopdt_step_response(t, k=2.0, tau=5.0, theta=1.0)
    # Within ~5τ after the dead time we should be within 1% of K.
    assert abs(y[-1] - 2.0) < 0.01
    # Before the dead time, y should still be 0.
    assert y[t < 0.5][0] == 0.0


def test_sopdt_response_handles_repeated_roots():
    t = np.linspace(0.0, 60.0, 121)
    y = sopdt_step_response(t, k=1.0, tau1=4.0, tau2=4.0, theta=0.0)
    assert np.all(np.isfinite(y))
    assert abs(y[-1] - 1.0) < 0.01


# ── Fitting -----------------------------------------------------------------


def test_fit_fopdt_recovers_known_params():
    st, true = _make_fopdt_steptest(k=2.5, tau=8.0, theta=1.5, pre=10.0, noise=0.005)
    model = fit_fopdt(st)
    assert model.model_type == "FOPDT"
    p = model.parameters
    assert p["gain"] == pytest.approx(true["k"], abs=0.05)
    assert p["time_constant"] == pytest.approx(true["tau"], abs=0.5)
    # Fitted dead_time is measured from t[0] (the window start), so it includes
    # the pre-step duration.
    assert p["dead_time"] == pytest.approx(true["pre"] + true["theta"], abs=0.5)
    assert model.fit_quality is not None
    assert model.fit_quality > 0.99


def test_fit_sopdt_recovers_known_params():
    st, true = _make_sopdt_steptest(noise=0.005)
    model = fit_sopdt(st)
    assert model.model_type == "SOPDT"
    p = model.parameters
    # Convention: tau1 >= tau2
    assert p["tau1"] >= p["tau2"]
    assert p["gain"] == pytest.approx(true["k"], abs=0.05)
    # Larger time constant should match true tau1 reasonably well.
    assert p["tau1"] == pytest.approx(true["tau1"], rel=0.15)
    assert model.fit_quality is not None
    assert model.fit_quality > 0.99


def test_identify_process_model_prefers_fopdt_for_first_order_data():
    st, _ = _make_fopdt_steptest(noise=0.005)
    model = identify_process_model(st)
    # FOPDT should win by BIC because the extra SOPDT parameter is wasted.
    assert model.model_type == "FOPDT"


def test_identify_process_model_prefers_sopdt_for_second_order_data():
    st, _ = _make_sopdt_steptest(noise=0.005)
    model = identify_process_model(st)
    assert model.model_type == "SOPDT"


def test_least_squares_identifier_uses_candidates():
    st, _ = _make_sopdt_steptest(noise=0.005)
    ident = LeastSquaresIdentifier(candidates=("FOPDT",))
    model = ident.identify(st)
    assert model.model_type == "FOPDT"


def test_least_squares_identifier_rejects_wrong_input_type():
    ident = LeastSquaresIdentifier()
    with pytest.raises(TypeError):
        ident.identify({"not": "a step test"})


def test_fit_rejects_zero_step():
    t = np.linspace(0.0, 20.0, 60)
    u = np.zeros_like(t)
    y = np.zeros_like(t)
    with pytest.raises(ValueError):
        fit_fopdt(StepTest(t=t, u=u, y=y))


def test_step_test_validates_array_lengths():
    with pytest.raises(ValueError):
        StepTest(t=np.zeros(10), u=np.zeros(10), y=np.zeros(9))


# ── Step detection ----------------------------------------------------------


def test_detect_steps_finds_single_edge():
    u = np.concatenate([np.zeros(40), np.ones(60)])
    events = detect_steps(u)
    assert len(events) == 1
    e = events[0]
    assert 38 <= e.start_index <= 41
    assert e.magnitude == pytest.approx(1.0, abs=0.05)


def test_detect_steps_finds_multiple_edges():
    u = np.concatenate([np.zeros(30), np.full(30, 1.0), np.full(30, -1.0)])
    events = detect_steps(u, threshold=0.5)
    assert len(events) == 2


def test_detect_steps_handles_quiescent_signal():
    u = np.zeros(100)
    assert detect_steps(u) == []
