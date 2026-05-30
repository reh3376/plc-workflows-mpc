"""Public types for the MPC package — kept in their own module so concrete
implementations can import them without re-entering the package ``__init__``."""

from __future__ import annotations

import abc
from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True)
class PlantModel:
    """Discrete-time linear model used for prediction and estimation.

    ``x⁺ = A·x + Bu·u + Bd·d``, ``y = C·x`` at sample time ``ts``.
    ``Bd`` may have zero columns when no measured disturbance is present.
    """

    A: np.ndarray
    Bu: np.ndarray
    Bd: np.ndarray
    C: np.ndarray
    ts: float


@dataclass(frozen=True)
class MpcConfig:
    """MPC formulation and tuning parameters.

    Empty weight/limit tuples are filled with sensible defaults sized to the
    plant by :func:`~plc_workflows_mpc.apc.mpc.instantiate_mpc`.

    Attributes:
        prediction_horizon: steps to predict ahead (``Np``).
        control_horizon: number of free moves (``Nc ≤ Np``).
        q: CV tracking weight per controlled variable.
        r_du: move-suppression weight per manipulated variable.
        u_min / u_max: hard setpoint clamps per MV.
        du_max: max |move| per cycle per MV.
        q_kf_state: process-noise covariance scaling for the model states.
        q_kf_dist: covariance scaling for the integrating output disturbance
            (higher = more aggressive unmeasured-disturbance rejection).
        r_kf_meas: measurement-noise covariance scaling.
    """

    prediction_horizon: int = 30
    control_horizon: int = 8
    q: tuple[float, ...] = ()
    r_du: tuple[float, ...] = ()
    u_min: tuple[float, ...] = ()
    u_max: tuple[float, ...] = ()
    du_max: tuple[float, ...] = ()
    q_kf_state: float = 1e-3
    q_kf_dist: float = 1e-1
    r_kf_meas: float = 1e-2
    extra: dict[str, float] = field(default_factory=dict)


class MpcController(abc.ABC):
    """A running MPC controller for one or more coupled control loops.

    Control-cycle call sequence (matches the reference implementation)::

        ctrl.estimate(y_meas, d_meas)        # correct state from feedback
        u = ctrl.solve(setpoint, d_meas)     # next MV/setpoint to write
        ctrl.commit(u)                        # remember what was applied
    """

    @abc.abstractmethod
    def reset(self, y_meas: np.ndarray, u_active: np.ndarray) -> None:
        """Bumpless arm: align estimator/last-input to the current process."""

    @abc.abstractmethod
    def estimate(self, y_meas: np.ndarray, d_meas: np.ndarray) -> None:
        """Predict-correct the augmented state from the latest measurement."""

    @abc.abstractmethod
    def solve(
        self,
        setpoint: np.ndarray,
        d_meas: np.ndarray,
        d_forecast: np.ndarray | None = None,
    ) -> np.ndarray:
        """Solve the receding-horizon QP and return the first MV move."""

    @abc.abstractmethod
    def commit(self, u_applied: np.ndarray) -> None:
        """Record the move actually applied this cycle."""


__all__ = ["PlantModel", "MpcConfig", "MpcController"]
