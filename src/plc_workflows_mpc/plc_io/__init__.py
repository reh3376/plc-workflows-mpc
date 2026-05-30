"""PLC link — Rockwell Logix I/O over EtherNet/IP.

Phase 2 ships the concrete :class:`LogixLink` (backed by ``pycomm3``'s
``LogixDriver`` over EtherNet/IP — TCP 44818, explicit messaging — no RSLinx or
Studio 5000 SDK at runtime), plus the abstract :class:`PlcLink` that lets unit
tests substitute a fake. ``pycomm3`` ships in the ``apc`` optional extra; the
base interfaces import without it.
"""

from __future__ import annotations

from plc_workflows_mpc.plc_io.base import CycleInputs, PlcLink
from plc_workflows_mpc.plc_io.logix import LogixLink, open_logix_link

__all__ = ["CycleInputs", "PlcLink", "LogixLink", "open_logix_link"]
