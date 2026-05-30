"""MPC / APC controller instantiation.

A constrained **linear** model-predictive controller that:
  * tracks controlled variable(s) (CV/PV) to a setpoint,
  * feeds *measured disturbances* (DV) forward through the model so their effect
    is countered before the CV deviates, and
  * uses an offset-free Kalman observer to reject *unmeasured* disturbances.

The plant is a discrete state-space model (sample time ``ts``)::

    x(k+1) = A x(k) + Bu u(k) + Bd d(k)
       y(k) = C x(k)

solved as a receding-horizon QP. Phase 2 ships:

* :class:`PlantModel`, :class:`MpcConfig`, and the :class:`MpcController` ABC
  (the public types — see :mod:`plc_workflows_mpc.apc.mpc.base`).
* :class:`LinearMpcController` — concrete OSQP-backed implementation
  (:mod:`plc_workflows_mpc.apc.mpc.controller`).
* :func:`instantiate_mpc` — convenience factory that fills empty weights/limits
  with sensible defaults sized to the plant.
* :func:`plant_model_from_identified` — convert a Phase-1 FOPDT/SOPDT
  ``ProcessModel`` into a discrete :class:`PlantModel` with dead-time delay
  buffer states (:mod:`plc_workflows_mpc.apc.mpc.realization`).

The runtime stack — OSQP and the Rockwell EtherNet/IP link — lives in the
``apc`` optional extra. Install with ``uv pip install -e ".[apc]"``.
"""

from __future__ import annotations

from plc_workflows_mpc.apc.mpc.base import MpcConfig, MpcController, PlantModel
from plc_workflows_mpc.apc.mpc.controller import LinearMpcController, instantiate_mpc
from plc_workflows_mpc.apc.mpc.realization import plant_model_from_identified

__all__ = [
    "PlantModel",
    "MpcConfig",
    "MpcController",
    "LinearMpcController",
    "instantiate_mpc",
    "plant_model_from_identified",
]
