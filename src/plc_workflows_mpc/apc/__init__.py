"""Pillar 3 — Advanced Process Control.

Three stages:
  * :mod:`plc_workflows_mpc.apc.identification` — identify a process model from
    operating data (FOPDT / SOPDT / state-space).
  * :mod:`plc_workflows_mpc.apc.selection` — recommend the right control
    strategy (PID / APC / MPC) for an identified process.
  * :mod:`plc_workflows_mpc.apc.mpc` — instantiate and run MPC controllers.

Phase 1 ships ``identification`` and ``selection`` as concrete implementations
(see their module docstrings). ``mpc`` is interface-only until Phase 2.
"""

from __future__ import annotations

from plc_workflows_mpc.apc.identification import ModelIdentifier, ProcessModel
from plc_workflows_mpc.apc.mpc import MpcConfig, MpcController, PlantModel
from plc_workflows_mpc.apc.selection import ControlStrategy, recommend_strategy

__all__ = [
    "ModelIdentifier",
    "ProcessModel",
    "ControlStrategy",
    "recommend_strategy",
    "PlantModel",
    "MpcConfig",
    "MpcController",
]
