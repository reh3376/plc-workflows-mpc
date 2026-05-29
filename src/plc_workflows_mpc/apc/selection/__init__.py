"""Control strategy selection.

Given an identified :class:`~plc_workflows_mpc.apc.identification.ProcessModel`,
recommend the appropriate control strategy for the process — the "process
analysis for determining the correct MPC/APC algorithm" pillar.

Phase 1 implements :func:`recommend_strategy`; Phase 0 defines the contract.
"""

from __future__ import annotations

from enum import StrEnum

from plc_workflows_mpc.apc.identification import ProcessModel


class ControlStrategy(StrEnum):
    """Candidate control strategies, in increasing order of sophistication."""

    PID = "PID"
    APC = "APC"
    MPC = "MPC"


def recommend_strategy(model: ProcessModel) -> ControlStrategy:
    """Recommend a control strategy for an identified process model.

    Implemented in Phase 1 (e.g. based on dead-time/time-constant ratio,
    interaction, constraints, and number of manipulated variables).
    """
    raise NotImplementedError("Strategy selection lands in Phase 1.")


__all__ = ["ControlStrategy", "recommend_strategy"]
