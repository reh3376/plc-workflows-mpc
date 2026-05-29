"""Process model identification.

Identify a dynamic process model (FOPDT / SOPDT) from step-test or operating
data, so the selection stage can recommend a control strategy and the MPC stage
has a model to predict with.

Phase 1 ships a :func:`identify_process_model` (NLS over FOPDT and SOPDT with
BIC selection), a :func:`detect_steps` helper to slice operating data into
step-test windows, and a concrete :class:`LeastSquaresIdentifier`.
"""

from __future__ import annotations

from plc_workflows_mpc.apc.identification.base import ModelIdentifier, ProcessModel
from plc_workflows_mpc.apc.identification.fit import (
    LeastSquaresIdentifier,
    StepTest,
    fit_fopdt,
    fit_sopdt,
    identify_process_model,
)
from plc_workflows_mpc.apc.identification.models import (
    fopdt_step_response,
    sopdt_step_response,
)
from plc_workflows_mpc.apc.identification.step_detection import StepEvent, detect_steps

__all__ = [
    "ProcessModel",
    "ModelIdentifier",
    "LeastSquaresIdentifier",
    "StepTest",
    "StepEvent",
    "detect_steps",
    "fit_fopdt",
    "fit_sopdt",
    "identify_process_model",
    "fopdt_step_response",
    "sopdt_step_response",
]
