"""Pillar 2 — PLC SDLC.

Bring PLC development in line with standard software development: represent PLC
programs in git-friendly text (L5X / ACD ↔ JSON), and generate CI/CD pipelines
for PLC code (lint, diff, validate, deploy). Reuses the existing
``plc-format-converter`` tooling for the conversion layer.

Phase 3 implements these; Phase 0 defines the contract.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def export_to_git_format(plc_file: Path) -> Path:
    """Convert a binary/L5X PLC export into a git-tracked text representation."""
    raise NotImplementedError("PLC SDLC format export lands in Phase 3.")


def import_from_git_format(git_file: Path) -> Path:
    """Rebuild a PLC-importable artifact from its git-tracked representation."""
    raise NotImplementedError("PLC SDLC format import lands in Phase 3.")


def generate_pipeline(project_config: dict[str, Any]) -> str:
    """Generate a CI/CD pipeline definition for a PLC project."""
    raise NotImplementedError("PLC SDLC pipeline generation lands in Phase 3.")


__all__ = ["export_to_git_format", "import_from_git_format", "generate_pipeline"]
