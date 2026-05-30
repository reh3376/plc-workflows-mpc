"""Generate CI/CD pipeline templates for PLC project repos.

A customer-side PLC repo that follows the L5X-as-source-of-truth pattern can
drop the generated workflow into ``.github/workflows/`` and immediately get:

* parse validation on every L5X file (catches export corruption),
* round-trip equivalence check (parse → render → re-parse),
* an optional diff report between the PR head and the base branch so
  reviewers can see *structural* changes rather than wading through XML.

The generator emits plain YAML as a string — no PyYAML dependency — so it's
deterministic, easy to test, and easy for customers to edit by hand.
"""

from __future__ import annotations

import shlex
from collections.abc import Iterable

from plc_workflows_mpc.sdlc.base import PipelineConfig

_INDENT = "  "


def generate_github_workflow(config: PipelineConfig | None = None) -> str:
    """Render a GitHub Actions workflow YAML for a PLC project.

    Pass a :class:`PipelineConfig` to customize globs, the Python version, or
    additional steps; the default config produces a sensible baseline.
    """
    cfg = config or PipelineConfig()

    lines: list[str] = []
    lines.append(f"name: {cfg.name}")
    lines.append("")
    lines.append("on:")
    lines.append("  push:")
    lines.append("    branches: [main]")
    lines.append("  pull_request:")
    lines.append("    branches: [main]")
    lines.append("")
    lines.append("jobs:")
    lines.append("  plc-ci:")
    lines.append("    runs-on: ubuntu-latest")
    lines.append("    steps:")
    lines.append("      - name: Checkout")
    lines.append("        uses: actions/checkout@v4")
    lines.append("        with:")
    lines.append("          fetch-depth: 0")
    lines.append("")
    lines.append("      - name: Set up Python")
    lines.append("        uses: actions/setup-python@v5")
    lines.append("        with:")
    lines.append(f"          python-version: '{cfg.python_version}'")
    lines.append("")
    lines.append("      - name: Install plc-workflows-mpc")
    lines.append("        run: pip install plc-workflows-mpc")
    lines.append("")

    if cfg.run_lint:
        lines.extend(
            _shell_step(
                name="Validate L5X files",
                glob=cfg.l5x_glob,
                subcommand="validate",
            )
        )

    if cfg.run_roundtrip_check:
        lines.extend(
            _shell_step(
                name="Round-trip check (L5X ↔ JSON)",
                glob=cfg.l5x_glob,
                subcommand="roundtrip",
            )
        )

    if cfg.run_diff_report:
        lines.extend(_diff_step(cfg.l5x_glob))

    for extra in cfg.extra_steps:
        lines.extend(_render_extra_step(extra))

    # Trailing newline so the file ends cleanly.
    return "\n".join(lines) + "\n"


def _shell_step(*, name: str, glob: str, subcommand: str) -> Iterable[str]:
    quoted = shlex.quote(glob)
    yield f"      - name: {name}"
    yield "        run: |"
    yield f"          mapfile -t FILES < <(find . -type f -path {quoted})"
    yield '          if [ "${#FILES[@]}" -eq 0 ]; then'
    yield f'            echo "No L5X files matched {glob}"; exit 0'
    yield "          fi"
    yield f"          python -m plc_workflows_mpc.sdlc {subcommand} \"${{FILES[@]}}\""
    yield ""


def _diff_step(glob: str) -> Iterable[str]:
    quoted = shlex.quote(glob)
    yield "      - name: PR structural diff report"
    yield "        if: github.event_name == 'pull_request'"
    yield "        run: |"
    yield "          BASE_SHA=${{ github.event.pull_request.base.sha }}"
    yield "          HEAD_SHA=${{ github.event.pull_request.head.sha }}"
    yield "          mapfile -t CHANGED < <("
    yield f"            git diff --name-only \"$BASE_SHA\" \"$HEAD_SHA\" -- {quoted}"
    yield "          )"
    yield '          if [ "${#CHANGED[@]}" -eq 0 ]; then'
    yield "            echo 'No L5X files changed in this PR.'; exit 0"
    yield "          fi"
    yield "          for f in \"${CHANGED[@]}\"; do"
    yield '            echo "--- diff: $f ---"'
    yield "            git show \"$BASE_SHA:$f\" > /tmp/base.L5X 2>/dev/null || continue"
    yield "            python -m plc_workflows_mpc.sdlc diff /tmp/base.L5X \"$f\" || true"
    yield "          done"
    yield ""


def _render_extra_step(extra: dict[str, object]) -> Iterable[str]:
    """Render an extra step. Supports {name, run} or {name, uses, with} keys."""
    yield f"      - name: {extra.get('name', 'extra step')}"
    if "uses" in extra:
        yield f"        uses: {extra['uses']}"
        with_block = extra.get("with")
        if isinstance(with_block, dict) and with_block:
            yield "        with:"
            for key, value in with_block.items():
                yield f"          {key}: {value}"
    if "run" in extra:
        run_text = str(extra["run"])
        if "\n" in run_text:
            yield "        run: |"
            for line in run_text.splitlines():
                yield f"          {line}"
        else:
            yield f"        run: {run_text}"
    yield ""


__all__ = ["generate_github_workflow"]
