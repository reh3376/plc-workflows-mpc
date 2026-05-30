"""Public types for the SDLC package — extracted to avoid circular imports."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

DiffOp = Literal["added", "removed", "changed"]


@dataclass(frozen=True)
class L5xDiffEntry:
    """A single textual difference between two L5X documents.

    ``path`` is a JSON-pointer-like dotted/bracketed path to the changed node;
    ``op`` is the kind of change; ``before`` / ``after`` are the value(s) at
    that path (``None`` when the path is added or removed).
    """

    path: str
    op: DiffOp
    before: object | None = None
    after: object | None = None


@dataclass(frozen=True)
class PipelineConfig:
    """Configuration for a generated PLC CI/CD pipeline."""

    name: str = "PLC Code CI"
    python_version: str = "3.12"
    l5x_glob: str = "plc/**/*.L5X"
    json_glob: str = "plc/**/*.l5x.json"
    run_lint: bool = True
    run_roundtrip_check: bool = True
    run_diff_report: bool = True
    extra_steps: tuple[dict[str, object], ...] = field(default_factory=tuple)
