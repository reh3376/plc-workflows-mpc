"""Pillar 4 — Plant-wide system optimization.

The top layer: coordinate all individual controllers toward a user-defined
plant objective (e.g. "maximize proof gallons produced") subject to process
and business constraints. This real-time optimization (RTO) layer sits above
the MPC controllers and adjusts their setpoints.

Phase 4 implements :class:`PlantOptimizer`; Phase 0 defines the contract.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ObjectiveSense(StrEnum):
    """Whether the plant objective is maximized or minimized."""

    MAXIMIZE = "maximize"
    MINIMIZE = "minimize"


@dataclass(frozen=True)
class OptimizationObjective:
    """A user-defined plant-wide optimization objective.

    Attributes:
        name: human-readable objective name (e.g. "proof_gallons").
        sense: maximize or minimize.
        target_variable: the variable the objective evaluates.
        constraints: process/business constraints to respect.
    """

    name: str
    sense: ObjectiveSense
    target_variable: str
    constraints: dict[str, Any] = field(default_factory=dict)


class PlantOptimizer(abc.ABC):
    """Coordinates controller setpoints to optimize a plant objective."""

    @abc.abstractmethod
    def optimize(self, plant_state: dict[str, float]) -> dict[str, float]:
        """Return recommended setpoints per loop given current plant state."""


def build_optimizer(objective: OptimizationObjective) -> PlantOptimizer:
    """Build a :class:`PlantOptimizer` for an objective — Phase 4."""
    raise NotImplementedError("Plant-wide optimization lands in Phase 4.")


__all__ = [
    "ObjectiveSense",
    "OptimizationObjective",
    "PlantOptimizer",
    "build_optimizer",
]
