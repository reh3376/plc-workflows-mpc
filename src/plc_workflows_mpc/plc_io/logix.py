"""Rockwell Logix link over EtherNet/IP via ``pycomm3``.

Isolates all EtherNet/IP I/O so the control logic in
:mod:`plc_workflows_mpc.supervisor` stays testable. Batches the per-cycle reads
into a single request, makes every write best-effort (returns success rather
than raising), and re-establishes the driver on connection loss.

``pycomm3`` is a soft import (available via the ``apc`` optional extra). If
``pycomm3`` is not installed, instantiating :class:`LogixLink` raises a clear
:class:`RuntimeError`; the rest of the package — including unit tests that use
``FakePlcLink`` — remains usable.
"""

from __future__ import annotations

import contextlib
import logging
from typing import Any

from plc_workflows_mpc.config import TagMap
from plc_workflows_mpc.plc_io.base import CycleInputs, PlcLink

log = logging.getLogger("plc_workflows_mpc.plc_io")

try:
    from pycomm3 import LogixDriver as _LogixDriver
except ImportError:  # pragma: no cover — soft dep
    _LogixDriver = None  # type: ignore[assignment,misc]


class LogixLink(PlcLink):
    """Production Rockwell Logix link backed by :class:`pycomm3.LogixDriver`."""

    def __init__(self, plc_path: str, tags: TagMap) -> None:
        if _LogixDriver is None:
            raise RuntimeError(
                "pycomm3 is not installed; LogixLink requires the 'apc' extra "
                "(uv pip install -e \".[apc]\")"
            )
        self._path = plc_path
        self._tags = tags
        self._plc = _LogixDriver(plc_path)
        self._plc.open()  # type: ignore[no-untyped-call]

    def read_cycle(self) -> CycleInputs:
        t = self._tags
        read_list = [
            t.enable,
            t.heartbeat_in,
            t.mv_feedback,
            t.setpoint_target,
            *t.cv,
            *t.dv,
        ]
        try:
            results = self._plc.read(*read_list)
            if not isinstance(results, list):
                results = [results]
            values = [r.value for r in results]
            ncv, ndv = len(t.cv), len(t.dv)
            base_offset = 4
            return CycleInputs(
                enabled=bool(values[0]),
                plc_heartbeat=int(values[1]),
                mv_feedback=float(values[2]),
                setpoint_target=float(values[3]),
                cv=[float(v) for v in values[base_offset : base_offset + ncv]],
                dv=[float(v) for v in values[base_offset + ncv : base_offset + ncv + ndv]],
                io_ok=True,
            )
        except Exception as exc:  # noqa: BLE001
            log.error("LogixLink.read_cycle failed: %s", exc)
            return CycleInputs(
                enabled=False,
                plc_heartbeat=0,
                mv_feedback=0.0,
                setpoint_target=0.0,
                cv=[],
                dv=[],
                io_ok=False,
            )

    def write(self, tag: str, value: Any) -> bool:
        try:
            self._plc.write(tag, value)
            return True
        except Exception as exc:  # noqa: BLE001
            log.error("LogixLink.write %s=%r failed: %s", tag, value, exc)
            return False

    def reconnect(self) -> None:
        log.warning("LogixLink reconnecting to %s", self._path)
        with contextlib.suppress(Exception):
            self._plc.close()  # type: ignore[no-untyped-call]
        try:
            self._plc.open()  # type: ignore[no-untyped-call]
        except Exception as exc:  # noqa: BLE001 — stay alive; next cycle retries
            log.error("LogixLink reconnect failed: %s", exc)

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self._plc.close()  # type: ignore[no-untyped-call]


def open_logix_link(plc_path: str, tags: TagMap) -> LogixLink:
    """Open a pycomm3-backed EtherNet/IP link to a Logix PLC."""
    return LogixLink(plc_path, tags)


__all__ = ["LogixLink", "open_logix_link"]
