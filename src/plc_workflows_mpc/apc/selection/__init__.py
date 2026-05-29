"""Control strategy selection.

Given an identified :class:`~plc_workflows_mpc.apc.identification.ProcessModel`
(and a few attributes of the process you can answer yes/no to), recommend the
appropriate control strategy: PID, APC (dead-time-compensated PID, e.g. Smith
predictor), or MPC.

Heuristic, tunable, and explainable — not a black box. The rules:

  1. Any **MIMO** loop, **hard MV/CV constraints**, or **measured disturbance to
     feed forward** ⇒ **MPC**. PID and unaugmented APC cannot coordinate
     multiple loops or honor constraints inside the optimization.
  2. Otherwise look at the dimensionless **dead-time ratio** θ/τ
     (effective dead time / dominant time constant):
       - θ/τ < ``apc_threshold`` (default 0.2) ⇒ **PID** is sufficient.
       - ``apc_threshold`` ≤ θ/τ < ``mpc_threshold`` (default 1.0) ⇒ **APC**
         (dead-time compensation buys real performance).
       - θ/τ ≥ ``mpc_threshold`` ⇒ **MPC** (dead-time-dominant; PID detunes
         heavily, MPC handles it natively).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from plc_workflows_mpc.apc.identification import ProcessModel


class ControlStrategy(StrEnum):
    """Candidate control strategies, in increasing order of sophistication."""

    PID = "PID"
    APC = "APC"
    MPC = "MPC"


@dataclass(frozen=True)
class SelectionRationale:
    """The recommendation plus the inputs and dimensionless metric used.

    Returned by :func:`recommend_strategy_with_rationale` for explainability.
    """

    strategy: ControlStrategy
    dead_time_ratio: float | None
    reason: str


def _effective_time_constant(model: ProcessModel) -> float | None:
    params = model.parameters
    if "time_constant" in params:
        return float(params["time_constant"])
    # SOPDT: use the dominant (larger) time constant.
    tau1 = params.get("tau1")
    tau2 = params.get("tau2")
    if tau1 is not None or tau2 is not None:
        return float(max(tau1 or 0.0, tau2 or 0.0))
    return None


def _dead_time_ratio(model: ProcessModel) -> float | None:
    tau = _effective_time_constant(model)
    theta = model.parameters.get("dead_time")
    if tau is None or theta is None or tau <= 0.0:
        return None
    return float(theta) / float(tau)


def recommend_strategy_with_rationale(
    model: ProcessModel,
    *,
    mimo: bool = False,
    has_measured_disturbance: bool = False,
    has_hard_constraints: bool = False,
    apc_threshold: float = 0.2,
    mpc_threshold: float = 1.0,
) -> SelectionRationale:
    """Recommend a control strategy and explain why."""
    if mimo:
        return SelectionRationale(
            ControlStrategy.MPC,
            _dead_time_ratio(model),
            "MIMO loop — PID/APC cannot coordinate multiple controllers.",
        )
    if has_hard_constraints:
        return SelectionRationale(
            ControlStrategy.MPC,
            _dead_time_ratio(model),
            "Hard MV/CV constraints — MPC honors them inside the optimization.",
        )
    if has_measured_disturbance:
        return SelectionRationale(
            ControlStrategy.MPC,
            _dead_time_ratio(model),
            "Measured disturbance to feed forward — MPC predicts and cancels.",
        )

    ratio = _dead_time_ratio(model)
    if ratio is None:
        return SelectionRationale(
            ControlStrategy.PID,
            None,
            "Insufficient model parameters to compute θ/τ; defaulting to PID.",
        )

    if ratio < apc_threshold:
        return SelectionRationale(
            ControlStrategy.PID,
            ratio,
            f"θ/τ = {ratio:.2f} < {apc_threshold} — PID is sufficient.",
        )
    if ratio < mpc_threshold:
        return SelectionRationale(
            ControlStrategy.APC,
            ratio,
            f"{apc_threshold} ≤ θ/τ = {ratio:.2f} < {mpc_threshold} — "
            "dead-time compensation (APC) buys real performance.",
        )
    return SelectionRationale(
        ControlStrategy.MPC,
        ratio,
        f"θ/τ = {ratio:.2f} ≥ {mpc_threshold} — dead-time-dominant; MPC wins.",
    )


def recommend_strategy(
    model: ProcessModel,
    *,
    mimo: bool = False,
    has_measured_disturbance: bool = False,
    has_hard_constraints: bool = False,
    apc_threshold: float = 0.2,
    mpc_threshold: float = 1.0,
) -> ControlStrategy:
    """Recommend a control strategy for an identified process model."""
    return recommend_strategy_with_rationale(
        model,
        mimo=mimo,
        has_measured_disturbance=has_measured_disturbance,
        has_hard_constraints=has_hard_constraints,
        apc_threshold=apc_threshold,
        mpc_threshold=mpc_threshold,
    ).strategy


__all__ = [
    "ControlStrategy",
    "SelectionRationale",
    "recommend_strategy",
    "recommend_strategy_with_rationale",
]
