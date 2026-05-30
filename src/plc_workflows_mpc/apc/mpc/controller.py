"""Constrained linear MPC controller on OSQP.

Implements :class:`~plc_workflows_mpc.apc.mpc.MpcController` for a discrete
state-space plant ``x⁺ = A·x + Bu·u + Bd·d``, ``y = C·x``:

* tracks controlled variable(s) to a setpoint,
* feeds *measured disturbances* forward through ``Bd`` (the optimizer pre-acts),
* uses an offset-free Kalman observer to reject *unmeasured* disturbances and
  remove steady-state error.

The receding-horizon QP is solved with OSQP. The cost matrix ``P`` is built
once at construction; only the linear term ``q`` and the rate bounds change
per cycle, so per-cycle solves are cheap and real-time friendly.

This module is the algorithmic heart of the spoke and is intentionally written
to be testable offline with no PLC or hub (``estimate → solve → commit`` with
plain numpy arrays).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import osqp
import scipy.sparse as sp
from scipy.linalg import solve_discrete_are

from plc_workflows_mpc.apc.mpc.base import MpcConfig, MpcController, PlantModel


@dataclass
class LinearMpcController(MpcController):
    """Constrained linear MPC with measured-disturbance feedforward."""

    model: PlantModel
    config: MpcConfig

    # Internal state (populated in __post_init__).
    x_hat: np.ndarray = field(init=False)
    p_hat: np.ndarray = field(init=False)
    u_prev: np.ndarray = field(init=False)

    def __post_init__(self) -> None:
        self._validate_config()
        self._build_prediction_matrices()
        self._build_estimator()
        self._build_static_qp()
        self.x_hat = np.zeros(self.model.A.shape[0])
        self.p_hat = np.zeros(self.model.C.shape[0])
        self.u_prev = np.zeros(self.model.Bu.shape[1])

    # ── Validation ─────────────────────────────────────────────

    def _validate_config(self) -> None:
        cfg, m = self.config, self.model
        nu, ny = m.Bu.shape[1], m.C.shape[0]
        if cfg.control_horizon < 1 or cfg.prediction_horizon < cfg.control_horizon:
            raise ValueError("Require 1 ≤ control_horizon ≤ prediction_horizon")
        if len(cfg.q) != ny:
            raise ValueError(f"weights.q must have length ny={ny}; got {len(cfg.q)}")
        if len(cfg.r_du) != nu:
            raise ValueError(f"weights.r_du must have length nu={nu}; got {len(cfg.r_du)}")
        for name, bound in (("u_min", cfg.u_min), ("u_max", cfg.u_max), ("du_max", cfg.du_max)):
            if len(bound) != nu:
                raise ValueError(f"limits.{name} must have length nu={nu}; got {len(bound)}")
        u_min = np.asarray(cfg.u_min, dtype=float)
        u_max = np.asarray(cfg.u_max, dtype=float)
        if np.any(u_min >= u_max):
            raise ValueError("Require u_min < u_max element-wise")

    # ── Prediction matrices ────────────────────────────────────

    def _build_prediction_matrices(self) -> None:
        m = self.model
        np_h, nc_h = self.config.prediction_horizon, self.config.control_horizon
        ny, nx, nu = m.C.shape[0], m.A.shape[0], m.Bu.shape[1]
        nd = m.Bd.shape[1]

        a_pow = [np.eye(nx)]
        for _ in range(np_h):
            a_pow.append(a_pow[-1] @ m.A)

        phi = np.zeros((np_h * ny, nx))
        gu = np.zeros((np_h * ny, nc_h * nu))
        gd = np.zeros((np_h * ny, np_h * nd))

        for j in range(1, np_h + 1):
            r0 = (j - 1) * ny
            phi[r0 : r0 + ny, :] = m.C @ a_pow[j]
            for i in range(j):
                ca = m.C @ a_pow[j - 1 - i]
                mi = min(i, nc_h - 1)
                cu = mi * nu
                gu[r0 : r0 + ny, cu : cu + nu] += ca @ m.Bu
                if nd:
                    cd = i * nd
                    gd[r0 : r0 + ny, cd : cd + nd] += ca @ m.Bd

        self._phi = phi
        self._gu = gu
        self._gd = gd
        self._nd = nd

    # ── Offset-free Kalman observer ────────────────────────────

    def _build_estimator(self) -> None:
        m = self.model
        nx, ny = m.A.shape[0], m.C.shape[0]
        aa = np.block([[m.A, np.zeros((nx, ny))], [np.zeros((ny, nx)), np.eye(ny)]])
        ca = np.hstack([m.C, np.eye(ny)])
        q_kf = np.block(
            [
                [self.config.q_kf_state * np.eye(nx), np.zeros((nx, ny))],
                [np.zeros((ny, nx)), self.config.q_kf_dist * np.eye(ny)],
            ]
        )
        r_kf = self.config.r_kf_meas * np.eye(ny)
        p_ric = solve_discrete_are(aa.T, ca.T, q_kf, r_kf)
        s = ca @ p_ric @ ca.T + r_kf
        kalman_gain = p_ric @ ca.T @ np.linalg.inv(s)
        self._aa = aa
        self._ca = ca
        self._l = kalman_gain

    # ── Static QP parts ────────────────────────────────────────

    def _build_static_qp(self) -> None:
        cfg, m = self.config, self.model
        nc_h = cfg.control_horizon
        nu = m.Bu.shape[1]

        q_bar = sp.kron(sp.eye(cfg.prediction_horizon), sp.diags(np.asarray(cfg.q, dtype=float)))
        r_bar = sp.kron(sp.eye(nc_h), sp.diags(np.asarray(cfg.r_du, dtype=float)))

        main = sp.eye(nc_h * nu)
        sub = sp.eye(nc_h * nu, k=-nu)
        self._diff_m = (main - sub).tocsc()
        self._sel_e = sp.vstack([sp.eye(nu), sp.csc_matrix((nc_h * nu - nu, nu))]).tocsc()

        gu_sp = sp.csc_matrix(self._gu)
        cost_p = 2.0 * (gu_sp.T @ q_bar @ gu_sp + self._diff_m.T @ r_bar @ self._diff_m)
        self._p_qp = sp.csc_matrix(cost_p)
        self._q_bar = q_bar
        self._r_bar = r_bar
        self._gu_sp = gu_sp

        a_ineq = sp.vstack([sp.eye(nc_h * nu), self._diff_m]).tocsc()
        n = nc_h * nu
        self._prob = osqp.OSQP()
        self._prob.setup(
            P=self._p_qp,
            q=np.zeros(n),
            A=a_ineq,
            l=np.full(2 * n, -1e6),
            u=np.full(2 * n, 1e6),
            verbose=False,
            polishing=False,
            eps_abs=1e-6,
            eps_rel=1e-6,
        )

    # ── Public API (MpcController) ─────────────────────────────

    def reset(self, y_meas: np.ndarray, u_active: np.ndarray) -> None:
        """Bumpless arm: align estimator/last-input to the current process."""
        y = np.atleast_1d(np.asarray(y_meas, dtype=float))
        self.u_prev = np.atleast_1d(np.asarray(u_active, dtype=float)).copy()
        self.x_hat = np.linalg.pinv(self.model.C) @ y
        self.p_hat = y - self.model.C @ self.x_hat

    def estimate(self, y_meas: np.ndarray, d_meas: np.ndarray) -> None:
        """Predict-correct the augmented state from the latest measurement."""
        m = self.model
        y = np.atleast_1d(np.asarray(y_meas, dtype=float))
        d = np.atleast_1d(np.asarray(d_meas, dtype=float)) if self._nd else np.zeros(0)
        z = np.concatenate([self.x_hat, self.p_hat])
        bu_aug = np.concatenate([m.Bu @ self.u_prev, np.zeros(m.C.shape[0])])
        bd_aug = np.concatenate(
            [m.Bd @ d if self._nd else np.zeros(m.A.shape[0]), np.zeros(m.C.shape[0])]
        )
        z_pred = self._aa @ z + bu_aug + bd_aug
        y_pred = self._ca @ z_pred
        z_new = z_pred + self._l @ (y - y_pred)
        self.x_hat = z_new[: m.A.shape[0]]
        self.p_hat = z_new[m.A.shape[0] :]

    def solve(
        self,
        setpoint: np.ndarray,
        d_meas: np.ndarray,
        d_forecast: np.ndarray | None = None,
    ) -> np.ndarray:
        """Solve the receding-horizon QP and return the first MV move."""
        cfg, m = self.config, self.model
        np_h, nc_h = cfg.prediction_horizon, cfg.control_horizon
        nu = m.Bu.shape[1]

        sp_vec = np.atleast_1d(np.asarray(setpoint, dtype=float))
        d = np.atleast_1d(np.asarray(d_meas, dtype=float)) if self._nd else np.zeros(0)

        if self._nd:
            if d_forecast is None:
                d_stack = np.tile(d, np_h)
            else:
                d_stack = np.asarray(d_forecast, dtype=float).reshape(np_h * self._nd)
        else:
            d_stack = np.zeros(0)

        r_stack = np.tile(sp_vec, np_h)
        p_stack = np.tile(self.p_hat, np_h)

        free = self._phi @ self.x_hat + p_stack - r_stack
        if self._nd:
            free = free + self._gd @ d_stack

        linear_q = 2.0 * (
            self._gu_sp.T @ self._q_bar @ free
            - (self._diff_m.T @ self._r_bar @ (self._sel_e @ self.u_prev))
        )

        n = nc_h * nu
        lb = np.empty(2 * n)
        ub = np.empty(2 * n)
        u_min = np.asarray(cfg.u_min, dtype=float)
        u_max = np.asarray(cfg.u_max, dtype=float)
        du_max = np.asarray(cfg.du_max, dtype=float)
        lb[:n] = np.tile(u_min, nc_h)
        ub[:n] = np.tile(u_max, nc_h)
        rate_lo = -np.tile(du_max, nc_h)
        rate_hi = np.tile(du_max, nc_h)
        e_u_prev = self._sel_e @ self.u_prev
        lb[n:] = rate_lo + e_u_prev
        ub[n:] = rate_hi + e_u_prev

        self._prob.update(q=np.asarray(linear_q).ravel(), l=lb, u=ub)
        res = self._prob.solve()
        status_val = self._osqp_status(res)
        if status_val not in (1, 2):
            return self.u_prev.copy()
        x_opt = np.asarray(res.x, dtype=float)
        return x_opt[:nu]

    def commit(self, u_applied: np.ndarray) -> None:
        """Record the move actually applied this cycle."""
        self.u_prev = np.atleast_1d(np.asarray(u_applied, dtype=float)).copy()

    # ── Helpers ────────────────────────────────────────────────

    @staticmethod
    def _osqp_status(res: Any) -> int:
        """Extract the OSQP integer status, tolerating OSQP API variants."""
        info = res.info
        for attr in ("status_val", "status_value"):
            val = getattr(info, attr, None)
            if isinstance(val, int):
                return val
        status_text = str(getattr(info, "status", "")).lower()
        if "solved" in status_text and "inaccurate" not in status_text:
            return 1
        if "inaccurate" in status_text:
            return 2
        return -1


def _as_tuple(values: Any, n: int, fill: float) -> tuple[float, ...]:
    """Coerce sequence/empty into a length-n tuple of floats with a default fill."""
    if not values:
        return tuple([fill] * n)
    out = tuple(float(v) for v in values)
    if len(out) != n:
        raise ValueError(f"expected length {n}, got {len(out)}")
    return out


def instantiate_mpc(model: PlantModel, config: MpcConfig) -> LinearMpcController:
    """Build a :class:`LinearMpcController` for the given plant and config.

    Empty weight/limit tuples in ``config`` are filled with sensible defaults
    (unit weights, ±∞ bounds, infinite rate) sized to the plant dimensions, so
    the caller can supply only what they want to override.
    """
    nu, ny = model.Bu.shape[1], model.C.shape[0]
    populated = MpcConfig(
        prediction_horizon=config.prediction_horizon,
        control_horizon=config.control_horizon,
        q=_as_tuple(config.q, ny, 1.0),
        r_du=_as_tuple(config.r_du, nu, 0.1),
        u_min=_as_tuple(config.u_min, nu, -np.inf),
        u_max=_as_tuple(config.u_max, nu, np.inf),
        du_max=_as_tuple(config.du_max, nu, np.inf),
        q_kf_state=config.q_kf_state,
        q_kf_dist=config.q_kf_dist,
        r_kf_meas=config.r_kf_meas,
        extra=config.extra,
    )
    return LinearMpcController(model=model, config=populated)


__all__ = ["LinearMpcController", "instantiate_mpc"]
