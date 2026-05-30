"""Pillar 2 — PLC SDLC.

Bring PLC development in line with standard software development: represent
Rockwell Studio 5000 projects in a git-tracked text form (L5X XML ↔ a
deterministic JSON shape), validate them in CI, and ship a GitHub Actions
workflow template customers can drop into their PLC project repos. The
PLC-side integration templates (Structured Text routine, ladder description,
controller-tag CSV) live at the repository root under ``plc/templates/``.

Phase 3 ships:

* :mod:`plc_workflows_mpc.sdlc.conversion` — :func:`l5x_to_dict` /
  :func:`dict_to_l5x` with round-trip preservation; file helpers
  (:func:`convert_l5x_file_to_json`, :func:`convert_json_file_to_l5x`);
  :func:`validate_l5x`; :func:`l5x_diff` for structural diffs.
* :mod:`plc_workflows_mpc.sdlc.pipelines` — :func:`generate_github_workflow`
  renders a CI workflow YAML driven by :class:`PipelineConfig`.
* :mod:`plc_workflows_mpc.sdlc.cli` — the ``python -m plc_workflows_mpc.sdlc``
  CLI used by the generated pipeline.

Binary ``.ACD`` conversion (Rockwell's native format) requires Studio 5000 or an
external tool; this package handles the L5X / JSON layer once you have an L5X
export.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from plc_workflows_mpc.sdlc.base import L5xDiffEntry, PipelineConfig
from plc_workflows_mpc.sdlc.conversion import (
    convert_json_file_to_l5x,
    convert_l5x_file_to_json,
    dict_to_l5x,
    l5x_diff,
    l5x_to_dict,
    read_json,
    validate_l5x,
    write_json,
)
from plc_workflows_mpc.sdlc.pipelines import generate_github_workflow


def export_to_git_format(plc_file: Path) -> Path:
    """Convert an L5X export into a git-tracked JSON representation alongside it.

    The output is written next to ``plc_file`` with the suffix ``.l5x.json``.
    """
    json_path = plc_file.with_suffix(plc_file.suffix + ".json")
    return convert_l5x_file_to_json(plc_file, json_path)


def import_from_git_format(git_file: Path) -> Path:
    """Rebuild an L5X file from its git-tracked JSON representation."""
    target = git_file.with_suffix("")
    if target.suffix == "":
        target = target.with_suffix(".L5X")
    return convert_json_file_to_l5x(git_file, target)


def generate_pipeline(project_config: dict[str, Any]) -> str:
    """Generate a GitHub Actions workflow YAML for a PLC project repo.

    ``project_config`` is a plain dict mirroring :class:`PipelineConfig`'s
    fields. Unknown keys are ignored.
    """
    fields = {f for f in PipelineConfig.__dataclass_fields__}
    filtered = {k: v for k, v in project_config.items() if k in fields}
    return generate_github_workflow(PipelineConfig(**filtered))


__all__ = [
    "L5xDiffEntry",
    "PipelineConfig",
    "l5x_to_dict",
    "dict_to_l5x",
    "convert_l5x_file_to_json",
    "convert_json_file_to_l5x",
    "read_json",
    "write_json",
    "validate_l5x",
    "l5x_diff",
    "generate_github_workflow",
    "export_to_git_format",
    "import_from_git_format",
    "generate_pipeline",
]
