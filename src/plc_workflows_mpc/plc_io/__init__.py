"""PLC link — Rockwell Logix I/O over EtherNet/IP.

Isolates all PLC communication behind a small interface so the control logic
stays testable. The production implementation (Phase 2) uses ``pycomm3``'s
``LogixDriver`` over EtherNet/IP (TCP 44818, explicit messaging — no RSLinx or
Studio 5000 SDK at runtime), batching the per-cycle reads into a single request
and re-establishing the driver on connection loss.

Phase 2 implements a concrete :class:`PlcLink`; Phase 0 defines the contract.
``pycomm3`` ships in the ``apc`` optional extra.
"""

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


def open_logix_link(plc_path: str, tags: Any) -> PlcLink:
    """Open a pycomm3-backed EtherNet/IP link to a Logix PLC — Phase 2."""
    raise NotImplementedError("EtherNet/IP (pycomm3) link lands in Phase 2.")


__all__ = ["CycleInputs", "PlcLink", "open_logix_link"]
