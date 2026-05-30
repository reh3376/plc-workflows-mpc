"""Convert identified FOPDT / SOPDT process models into state-space PlantModels.

Discretizes the canonical continuous transfer functions at sample time ``ts``
and lifts the dead time into a delay buffer (one extra state per sample of
delay). This is the bridge from Phase 1 identification to Phase 2 control.
"""

from __future__ import annotations

import numpy as np
from scipy.signal import cont2discrete

from plc_workflows_mpc.apc.identification import ProcessModel
from plc_workflows_mpc.apc.mpc.base import PlantModel

_EPS = 1e-12


def plant_model_from_identified(model: ProcessModel, ts: float) -> PlantModel:
    """Realize an identified model as a discrete-time :class:`PlantModel`.

    Dead time ``θ`` is rounded to ``n_d = round(θ / ts)`` samples and added as
    a unit-delay buffer prepended to the dynamic state. ``Bd`` is empty
    (no measured disturbance) because the Phase-1 identifier does not yet
    fit DV→y dynamics; populate it manually for feedforward.
    """
    if ts <= 0.0:
        raise ValueError("ts must be positive")
    if model.model_type == "FOPDT":
        return _fopdt_to_plant(model, ts)
    if model.model_type == "SOPDT":
        return _sopdt_to_plant(model, ts)
    raise NotImplementedError(
        f"State-space realization for model_type={model.model_type!r} not supported"
    )


def _dead_time_samples(theta: float, ts: float) -> int:
    return int(round(max(theta, 0.0) / ts))


def _augment_with_delay(
    a_dyn: np.ndarray, bu_dyn: np.ndarray, c_dyn: np.ndarray, n_d: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Prepend ``n_d`` unit-delay states ahead of the dynamic states.

    State layout after augmentation:
        x = [x_dyn (size nx_dyn) | u_buf (size n_d)]
    where ``u_buf[i]`` holds ``u(k − i − 1)``. The dynamic update consumes
    ``u(k − n_d) = u_buf[n_d − 1]``; the new input feeds ``u_buf[0]``.
    For ``n_d == 0`` the matrices are returned unchanged.
    """
    if n_d <= 0:
        return a_dyn, bu_dyn, c_dyn

    nx_dyn = a_dyn.shape[0]
    nu = bu_dyn.shape[1]
    nx = nx_dyn + n_d * nu

    a_aug = np.zeros((nx, nx))
    bu_aug = np.zeros((nx, nu))
    c_aug = np.zeros((c_dyn.shape[0], nx))

    # Top-left: original A.
    a_aug[:nx_dyn, :nx_dyn] = a_dyn
    # Dynamic update reads the oldest buffered input: column block for u_buf[n_d-1].
    last_block_col = nx_dyn + (n_d - 1) * nu
    a_aug[:nx_dyn, last_block_col : last_block_col + nu] = bu_dyn

    # New input feeds the newest buffer slot (u_buf[0]).
    bu_aug[nx_dyn : nx_dyn + nu, :] = np.eye(nu)

    # Shift register: u_buf[i] ← u_buf[i-1] for i = 1..n_d-1.
    for i in range(1, n_d):
        dst = nx_dyn + i * nu
        src = nx_dyn + (i - 1) * nu
        a_aug[dst : dst + nu, src : src + nu] = np.eye(nu)

    # Output map: unchanged on dynamic states.
    c_aug[:, :nx_dyn] = c_dyn
    return a_aug, bu_aug, c_aug


def _fopdt_to_plant(model: ProcessModel, ts: float) -> PlantModel:
    p = model.parameters
    k = float(p["gain"])
    tau = float(p["time_constant"])
    theta = float(p.get("dead_time", 0.0))
    if tau <= 0.0:
        raise ValueError("FOPDT time_constant must be positive")

    # ZOH discretization of K/(τs+1): y(k+1) = a y(k) + K(1-a) u(k).
    a_d = float(np.exp(-ts / max(tau, _EPS)))
    a_dyn = np.array([[a_d]])
    bu_dyn = np.array([[k * (1.0 - a_d)]])
    c_dyn = np.array([[1.0]])

    n_d = _dead_time_samples(theta, ts)
    a, bu, c = _augment_with_delay(a_dyn, bu_dyn, c_dyn, n_d)
    bd = np.zeros((a.shape[0], 0))
    return PlantModel(A=a, Bu=bu, Bd=bd, C=c, ts=ts)


def _sopdt_to_plant(model: ProcessModel, ts: float) -> PlantModel:
    p = model.parameters
    k = float(p["gain"])
    tau1 = float(p["tau1"])
    tau2 = float(p["tau2"])
    theta = float(p.get("dead_time", 0.0))
    if tau1 <= 0.0 or tau2 <= 0.0:
        raise ValueError("SOPDT tau1 and tau2 must be positive")

    # Continuous SOPDT G(s) = K / ((τ1 s + 1)(τ2 s + 1)) in controllable form.
    a_c = np.array(
        [
            [0.0, 1.0],
            [-1.0 / (tau1 * tau2), -(tau1 + tau2) / (tau1 * tau2)],
        ]
    )
    b_c = np.array([[0.0], [1.0]])
    c_c = np.array([[k / (tau1 * tau2), 0.0]])
    d_c = np.zeros((1, 1))

    a_d, bu_d, c_d, _, _ = cont2discrete((a_c, b_c, c_c, d_c), dt=ts, method="zoh")
    a_dyn = np.asarray(a_d, dtype=float)
    bu_dyn = np.asarray(bu_d, dtype=float)
    c_dyn = np.asarray(c_d, dtype=float)

    n_d = _dead_time_samples(theta, ts)
    a, bu, c = _augment_with_delay(a_dyn, bu_dyn, c_dyn, n_d)
    bd = np.zeros((a.shape[0], 0))
    return PlantModel(A=a, Bu=bu, Bd=bd, C=c, ts=ts)


__all__ = ["plant_model_from_identified"]
