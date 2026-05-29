"""Fit FOPDT / SOPDT process models to step-test data.

Uses ``scipy.optimize.curve_fit`` (Levenberg–Marquardt with bounds) against the
canonical step responses, with robust initial guesses derived from steady-state
gain, the time-to-first-response, and the 63 % rise time. Reports R², RMSE,
AIC, and BIC so the public :func:`identify_process_model` can choose between
FOPDT and SOPDT by lowest BIC.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.optimize import curve_fit

from plc_workflows_mpc.apc.identification.base import ModelIdentifier, ProcessModel
from plc_workflows_mpc.apc.identification.models import (
    fopdt_step_response,
    sopdt_step_response,
)

_MIN_SAMPLES = 6


@dataclass(frozen=True)
class StepTest:
    """A step-test window: aligned timestamps, input, and output arrays.

    The window should include at least ~10 % pre-step quiescent samples so the
    baseline (``u₀``, ``y₀``) is read from genuinely pre-step data; if the step
    falls inside the first decile, ``u_step`` is biased and the fitted gain is
    scaled. Pre-detect the step with :func:`detect_steps` and slice accordingly.
    """

    t: np.ndarray
    u: np.ndarray
    y: np.ndarray

    def __post_init__(self) -> None:
        t = np.asarray(self.t, dtype=float).ravel()
        u = np.asarray(self.u, dtype=float).ravel()
        y = np.asarray(self.y, dtype=float).ravel()
        if not (t.size == u.size == y.size):
            raise ValueError("StepTest arrays t, u, y must have the same length")
        if t.size < _MIN_SAMPLES:
            raise ValueError(f"StepTest needs at least {_MIN_SAMPLES} samples")
        object.__setattr__(self, "t", t)
        object.__setattr__(self, "u", u)
        object.__setattr__(self, "y", y)


@dataclass
class _Baseline:
    u0: float
    y0: float
    u_step: float
    y_final: float


def _baseline(step_test: StepTest) -> _Baseline:
    n = step_test.t.size
    edge = max(1, n // 10)
    u0 = float(np.mean(step_test.u[:edge]))
    y0 = float(np.mean(step_test.y[:edge]))
    u_final = float(np.mean(step_test.u[-edge:]))
    y_final = float(np.mean(step_test.y[-edge:]))
    du = u_final - u0
    if abs(du) < 1e-12:
        raise ValueError("Step input magnitude is too small to identify a model")
    return _Baseline(u0=u0, y0=y0, u_step=du, y_final=y_final)


def _initial_guess(step_test: StepTest, base: _Baseline) -> dict[str, float]:
    t = step_test.t - step_test.t[0]
    y = step_test.y
    response_range = base.y_final - base.y0
    gain = response_range / base.u_step

    # Dead time: time-to-first-significant-response above noise.
    threshold = max(abs(response_range) * 0.05, 1e-9)
    deviating = np.nonzero(np.abs(y - base.y0) > threshold)[0]
    theta = float(t[int(deviating[0])]) if deviating.size else 0.0

    # Time constant: time to 63.2 % of the change, minus the dead time.
    target = base.y0 + 0.632 * response_range
    sign = math.copysign(1.0, response_range) if response_range != 0.0 else 1.0
    reached = np.nonzero(sign * (y - target) >= 0.0)[0]
    if reached.size:
        tau = max(float(t[int(reached[0])]) - theta, 1e-3)
    else:
        tau = max(float(t[-1] - theta) * 0.5, 1e-3)
    return {"gain": gain, "tau": tau, "theta": theta, "t_max": float(t[-1])}


def _fit_metrics(y: np.ndarray, y_hat: np.ndarray, *, k: int) -> dict[str, float]:
    n = int(y.size)
    residuals = y - y_hat
    ss_res = float(np.sum(residuals * residuals))
    ss_tot = float(np.sum((y - float(np.mean(y))) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    rmse = float(math.sqrt(ss_res / max(n, 1)))
    ln_arg = max(ss_res / max(n, 1), 1e-30)
    aic = n * math.log(ln_arg) + 2 * k
    bic = n * math.log(ln_arg) + k * math.log(max(n, 2))
    return {"r_squared": r2, "rmse": rmse, "aic": aic, "bic": bic, "n": float(n), "k": float(k)}


def fit_fopdt(step_test: StepTest) -> ProcessModel:
    """Fit a FOPDT model ``y(s)/u(s) = K e^(−θs)/(τs + 1)`` by NLS."""
    base = _baseline(step_test)
    guess = _initial_guess(step_test, base)
    t = step_test.t - step_test.t[0]
    y = step_test.y

    def f(t_: np.ndarray, k: float, tau: float, theta: float) -> np.ndarray:
        return fopdt_step_response(t_, k, tau, theta, u_step=base.u_step, y0=base.y0)

    p0: list[float] = [guess["gain"], guess["tau"], guess["theta"]]
    lower = [-np.inf, 1e-6, 0.0]
    upper = [np.inf, np.inf, max(guess["t_max"], 1e-3)]
    try:
        popt, _ = curve_fit(f, t, y, p0=p0, bounds=(lower, upper), maxfev=10_000)
    except (RuntimeError, ValueError) as exc:
        raise RuntimeError(f"FOPDT curve_fit failed: {exc}") from exc

    k_hat, tau_hat, theta_hat = float(popt[0]), float(popt[1]), float(popt[2])
    y_hat = f(t, k_hat, tau_hat, theta_hat)
    metrics = _fit_metrics(y, y_hat, k=3)
    return ProcessModel(
        model_type="FOPDT",
        parameters={"gain": k_hat, "time_constant": tau_hat, "dead_time": theta_hat},
        fit_quality=metrics["r_squared"],
        metadata={**metrics, "step_magnitude": base.u_step, "y0": base.y0},
    )


def fit_sopdt(step_test: StepTest) -> ProcessModel:
    """Fit an overdamped SOPDT model by NLS, with τ1 ≥ τ2 by convention."""
    base = _baseline(step_test)
    guess = _initial_guess(step_test, base)
    t = step_test.t - step_test.t[0]
    y = step_test.y

    def f(t_: np.ndarray, k: float, tau1: float, tau2: float, theta: float) -> np.ndarray:
        return sopdt_step_response(t_, k, tau1, tau2, theta, u_step=base.u_step, y0=base.y0)

    p0: list[float] = [guess["gain"], guess["tau"], guess["tau"] * 0.5, guess["theta"]]
    lower = [-np.inf, 1e-6, 1e-6, 0.0]
    upper = [np.inf, np.inf, np.inf, max(guess["t_max"], 1e-3)]
    try:
        popt, _ = curve_fit(f, t, y, p0=p0, bounds=(lower, upper), maxfev=10_000)
    except (RuntimeError, ValueError) as exc:
        raise RuntimeError(f"SOPDT curve_fit failed: {exc}") from exc

    k_hat = float(popt[0])
    tau1 = float(popt[1])
    tau2 = float(popt[2])
    theta_hat = float(popt[3])
    if tau1 < tau2:
        tau1, tau2 = tau2, tau1

    y_hat = f(t, k_hat, tau1, tau2, theta_hat)
    metrics = _fit_metrics(y, y_hat, k=4)
    return ProcessModel(
        model_type="SOPDT",
        parameters={"gain": k_hat, "tau1": tau1, "tau2": tau2, "dead_time": theta_hat},
        fit_quality=metrics["r_squared"],
        metadata={**metrics, "step_magnitude": base.u_step, "y0": base.y0},
    )


_FITTERS: dict[str, Callable[[StepTest], ProcessModel]] = {
    "FOPDT": fit_fopdt,
    "SOPDT": fit_sopdt,
}


def identify_process_model(
    time_series: StepTest,
    *,
    candidates: tuple[str, ...] = ("FOPDT", "SOPDT"),
) -> ProcessModel:
    """Fit each candidate model and return the one with the lowest BIC.

    ``time_series`` must be a :class:`StepTest`. Raises :class:`RuntimeError`
    if every candidate fit fails.
    """
    fits: list[ProcessModel] = []
    last_exc: Exception | None = None
    for name in candidates:
        fitter = _FITTERS.get(name)
        if fitter is None:
            continue
        try:
            fits.append(fitter(time_series))
        except Exception as exc:  # noqa: BLE001 — keep trying remaining candidates
            last_exc = exc
    if not fits:
        raise RuntimeError(f"All candidate model fits failed: {last_exc}")
    return min(fits, key=lambda m: _bic_of(m))


def _bic_of(model: ProcessModel) -> float:
    value = model.metadata.get("bic")
    return float(value) if isinstance(value, int | float) else float("inf")


@dataclass
class LeastSquaresIdentifier(ModelIdentifier):
    """Concrete :class:`ModelIdentifier` using NLS over FOPDT/SOPDT candidates."""

    candidates: tuple[str, ...] = ("FOPDT", "SOPDT")

    def identify(self, time_series: Any) -> ProcessModel:
        if not isinstance(time_series, StepTest):
            raise TypeError(
                "LeastSquaresIdentifier.identify expects a StepTest; "
                f"got {type(time_series).__name__}"
            )
        return identify_process_model(time_series, candidates=self.candidates)


__all__ = [
    "StepTest",
    "fit_fopdt",
    "fit_sopdt",
    "identify_process_model",
    "LeastSquaresIdentifier",
]
