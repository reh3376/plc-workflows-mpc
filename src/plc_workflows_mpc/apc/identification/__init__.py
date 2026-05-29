"""Process model identification.

Identify a dynamic process model from operating / step-test data so the
selection and MPC stages have something to reason about. Generalizes the
control-loop analysis from the predecessor project (FOPDT / SOPDT fitting,
step detection, fit-quality scoring).

Phase 1 implements :class:`ModelIdentifier`; Phase 0 defines the contract.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ProcessModel:
    """An identified dynamic process model.

    Attributes:
        model_type: e.g. ``"FOPDT"``, ``"SOPDT"``, ``"state_space"``.
        parameters: model parameters (e.g. gain, time_constant, dead_time).
        fit_quality: goodness-of-fit metric (e.g. R²), if computed.
        metadata: free-form provenance (loop_id, data window, method).
    """

    model_type: str
    parameters: dict[str, float]
    fit_quality: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class ModelIdentifier(abc.ABC):
    """Identifies a :class:`ProcessModel` from time-series operating data."""

    @abc.abstractmethod
    def identify(self, time_series: Any) -> ProcessModel:
        """Fit a process model to the supplied time series."""


def identify_process_model(time_series: Any) -> ProcessModel:
    """Convenience entry point — implemented in Phase 1."""
    raise NotImplementedError("Process model identification lands in Phase 1.")


__all__ = ["ProcessModel", "ModelIdentifier", "identify_process_model"]
