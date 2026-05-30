"""Shared in-memory fakes for Phase 2 tests."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from plc_workflows_mpc.apc.mpc.base import MpcController
from plc_workflows_mpc.plc_io.base import CycleInputs, PlcLink


@dataclass
class FakePlcLink(PlcLink):
    """In-memory PLC link driven by a scripted list of cycles.

    ``cycles`` is consumed left-to-right by :meth:`read_cycle`. Once exhausted,
    further reads return a quiescent disabled cycle. ``writes`` records every
    ``(tag, value)`` so tests can assert what was sent.
    """

    cycles: list[CycleInputs] = field(default_factory=list)
    writes: list[tuple[str, Any]] = field(default_factory=list)
    _cursor: int = 0
    closed: bool = False
    reconnect_count: int = 0
    on_read: Callable[[CycleInputs], CycleInputs] | None = None

    def read_cycle(self) -> CycleInputs:
        if self._cursor < len(self.cycles):
            cycle = self.cycles[self._cursor]
            self._cursor += 1
        else:
            cycle = CycleInputs(
                enabled=False, plc_heartbeat=0, mv_feedback=0.0, setpoint_target=0.0
            )
        return self.on_read(cycle) if self.on_read else cycle

    def write(self, tag: str, value: Any) -> bool:
        self.writes.append((tag, value))
        return True

    def reconnect(self) -> None:
        self.reconnect_count += 1

    def close(self) -> None:
        self.closed = True


def make_cycle(
    *,
    enabled: bool = True,
    hb: int = 0,
    mv_feedback: float = 0.0,
    setpoint_target: float = 0.0,
    cv: tuple[float, ...] = (0.0,),
    dv: tuple[float, ...] = (),
    io_ok: bool = True,
) -> CycleInputs:
    """Build a CycleInputs with the common defaults filled in."""
    return CycleInputs(
        enabled=enabled,
        plc_heartbeat=hb,
        mv_feedback=mv_feedback,
        setpoint_target=setpoint_target,
        cv=list(cv),
        dv=list(dv),
        io_ok=io_ok,
    )


@dataclass
class FakeMpcController(MpcController):
    """A trivial MPC stand-in for supervisor tests.

    ``solve`` returns ``constant_move`` regardless of inputs. ``reset``,
    ``estimate``, and ``commit`` record their args so tests can assert what
    the supervisor passed in.
    """

    constant_move: float = 1.0
    reset_calls: list[tuple[np.ndarray, np.ndarray]] = field(default_factory=list)
    estimate_calls: list[tuple[np.ndarray, np.ndarray]] = field(default_factory=list)
    solve_calls: list[tuple[np.ndarray, np.ndarray]] = field(default_factory=list)
    committed: list[np.ndarray] = field(default_factory=list)

    def reset(self, y_meas: np.ndarray, u_active: np.ndarray) -> None:
        self.reset_calls.append((np.array(y_meas, copy=True), np.array(u_active, copy=True)))

    def estimate(self, y_meas: np.ndarray, d_meas: np.ndarray) -> None:
        self.estimate_calls.append((np.array(y_meas, copy=True), np.array(d_meas, copy=True)))

    def solve(
        self,
        setpoint: np.ndarray,
        d_meas: np.ndarray,
        d_forecast: np.ndarray | None = None,
    ) -> np.ndarray:
        self.solve_calls.append((np.array(setpoint, copy=True), np.array(d_meas, copy=True)))
        return np.array([self.constant_move])

    def commit(self, u_applied: np.ndarray) -> None:
        self.committed.append(np.array(u_applied, copy=True))


__all__ = ["FakePlcLink", "FakeMpcController", "make_cycle"]
