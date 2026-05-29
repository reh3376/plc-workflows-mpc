"""Canonical step responses for FOPDT and SOPDT process models.

These are the analytic step responses used both for fitting (the curve
``curve_fit`` matches against measurement) and for forward simulation.
"""

from __future__ import annotations

import numpy as np

_EPS = 1e-12


def fopdt_step_response(
    t: np.ndarray,
    k: float,
    tau: float,
    theta: float,
    *,
    u_step: float = 1.0,
    y0: float = 0.0,
) -> np.ndarray:
    """First-Order Plus Dead Time step response.

    ``y(t) = y0 + k · u_step · (1 − exp(−(t − θ)/τ))`` for ``t ≥ θ``.
    """
    t = np.asarray(t, dtype=float)
    y = np.full_like(t, y0, dtype=float)
    mask = t >= theta
    y[mask] = y0 + k * u_step * (1.0 - np.exp(-(t[mask] - theta) / max(tau, _EPS)))
    return y


def sopdt_step_response(
    t: np.ndarray,
    k: float,
    tau1: float,
    tau2: float,
    theta: float,
    *,
    u_step: float = 1.0,
    y0: float = 0.0,
) -> np.ndarray:
    """Second-Order Plus Dead Time (overdamped) step response.

    Handles both distinct and (nearly) repeated real roots.
    """
    t = np.asarray(t, dtype=float)
    y = np.full_like(t, y0, dtype=float)
    mask = t >= theta
    tt = t[mask] - theta
    if abs(tau1 - tau2) < 1e-9:
        tau = max(tau1, _EPS)
        y[mask] = y0 + k * u_step * (1.0 - (1.0 + tt / tau) * np.exp(-tt / tau))
    else:
        t1 = max(tau1, _EPS)
        t2 = max(tau2, _EPS)
        y[mask] = y0 + k * u_step * (
            1.0 - (t1 * np.exp(-tt / t1) - t2 * np.exp(-tt / t2)) / (tau1 - tau2)
        )
    return y


__all__ = ["fopdt_step_response", "sopdt_step_response"]
