"""MPC / APC controller instantiation.

A constrained **linear** model-predictive controller that:
  * tracks controlled variable(s) (CV/PV) to a setpoint,
  * feeds *measured disturbances* (DV) forward through the model so their effect
    is countered before the CV deviates, and
  * uses an offset-free Kalman observer to reject *unmeasured* disturbances.

The plant is a discrete state-space model (sample time ``ts``)::

    x(k+1) = A x(k) + Bu u(k) + Bd d(k)
       y(k) = C x(k)

solved as a receding-horizon QP. This interface mirrors the proven
mpc-supervisor reference (OSQP solver, feedforward, offset-free observer) so the
Phase 2 implementation can drop straight in. The runtime control stack (OSQP)
ships in the ``apc`` optional extra.

Phase 2 implements :class:`MpcController`; Phase 0 defines the contract.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field

import numpy as np

from plc_workflows_mpc.apc.identification import ProcessModel


@dataclass(frozen=True)
class PlantModel:
    """Discrete-time linear model used for prediction and estimation."""

    A: np.ndarray
    Bu: np.ndarray
    Bd: np.ndarray
    C: np.ndarray
    ts: float


@dataclass(frozen=True)
class MpcConfig:
    """MPC formulation and tuning parameters.

    Attributes:
        prediction_horizon: steps to predict ahead (``Np``).
        control_horizon: number of free moves (``Nc ≤ Np``).
        q: CV tracking weight per controlled variable.
        r_du: move-suppression weight per manipulated variable.
        u_min / u_max: hard setpoint clamps per MV.
        du_max: max |move| per cycle per MV.
        q_kf_dist / r_kf_meas: offset-free observer covariances.
    """

    prediction_horizon: int = 30
    control_horizon: int = 8
    q: tuple[float, ...] = ()
    r_du: tuple[float, ...] = ()
    u_min: tuple[float, ...] = ()
    u_max: tuple[float, ...] = ()
    du_max: tuple[float, ...] = ()
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


def instantiate_mpc(model: PlantModel, config: MpcConfig) -> MpcController:
    """Build an :class:`MpcController` from a model + config — Phase 2."""
    raise NotImplementedError("MPC instantiation lands in Phase 2 (OSQP backend).")


def plant_model_from_identified(model: ProcessModel, ts: float) -> PlantModel:
    """Convert an identified :class:`ProcessModel` to a state-space PlantModel — Phase 1/2."""
    raise NotImplementedError("State-space realization lands in Phase 1/2.")


__all__ = [
    "PlantModel",
    "MpcConfig",
    "MpcController",
    "instantiate_mpc",
    "plant_model_from_identified",
]
