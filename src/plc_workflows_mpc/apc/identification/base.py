"""Public types for the identification package — kept in their own module so
submodules can import them without re-entering the package ``__init__``."""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ProcessModel:
    """An identified dynamic process model.

    Attributes:
        model_type: e.g. ``"FOPDT"``, ``"SOPDT"``, ``"state_space"``.
        parameters: model parameters (e.g. ``gain``, ``time_constant``,
            ``dead_time``, or ``tau1``/``tau2`` for SOPDT).
        fit_quality: goodness-of-fit metric (R²), if computed.
        metadata: free-form provenance (rmse, aic, bic, n, step magnitude, …).
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


__all__ = ["ProcessModel", "ModelIdentifier"]
