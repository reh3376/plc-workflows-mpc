"""Public types for the PLC I/O package — extracted to avoid circular imports."""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CycleInputs:
    """Everything read from the PLC in one batched cycle."""

    enabled: bool
    plc_heartbeat: int
    mv_feedback: float
    setpoint_target: float
    cv: list[float] = field(default_factory=list)
    dv: list[float] = field(default_factory=list)
    io_ok: bool = True


class PlcLink(abc.ABC):
    """Batched read / best-effort write / reconnecting PLC link."""

    @abc.abstractmethod
    def read_cycle(self) -> CycleInputs:
        """Batch-read enable, heartbeat, feedback, target, CVs and DVs."""

    @abc.abstractmethod
    def write(self, tag: str, value: Any) -> bool:
        """Best-effort write; returns success rather than raising."""

    @abc.abstractmethod
    def reconnect(self) -> None:
        """Re-establish the connection after a loss."""

    @abc.abstractmethod
    def close(self) -> None:
        """Close the connection."""


__all__ = ["CycleInputs", "PlcLink"]
