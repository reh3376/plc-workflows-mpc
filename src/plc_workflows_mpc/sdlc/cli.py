"""Argparse CLI for SDLC tasks — used by the generated CI pipeline.

Invoke via ``python -m plc_workflows_mpc.sdlc <command> [paths…]``.
Commands:

* ``validate`` — parse each L5X and check the root element.
* ``roundtrip`` — parse → serialize → re-parse, assert structural equality.
* ``to-json`` — write the JSON form alongside each L5X (``.l5x.json``).
* ``to-l5x`` — write the L5X form alongside each JSON.
* ``diff`` — structural diff of two L5X (or JSON) files.

Exit code 0 on success, 1 if any path failed.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from plc_workflows_mpc.sdlc.conversion import (
    convert_json_file_to_l5x,
    convert_l5x_file_to_json,
    dict_to_l5x,
    l5x_diff,
    l5x_to_dict,
    read_json,
    validate_l5x,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="plc-workflows-mpc-sdlc",
        description="L5X ↔ JSON conversion / validation for PLC CI pipelines.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_val = sub.add_parser("validate", help="Validate one or more L5X files.")
    p_val.add_argument("paths", nargs="+", type=Path)

    p_rt = sub.add_parser("roundtrip", help="Parse → serialize → re-parse for equivalence.")
    p_rt.add_argument("paths", nargs="+", type=Path)

    p_tj = sub.add_parser("to-json", help="Write the JSON form alongside each L5X.")
    p_tj.add_argument("paths", nargs="+", type=Path)

    p_tl = sub.add_parser("to-l5x", help="Write the L5X form alongside each JSON.")
    p_tl.add_argument("paths", nargs="+", type=Path)

    p_diff = sub.add_parser("diff", help="Structural diff between two L5X (or JSON) files.")
    p_diff.add_argument("a", type=Path)
    p_diff.add_argument("b", type=Path)

    args = parser.parse_args(argv)
    if args.cmd == "validate":
        return _cmd_validate(args.paths)
    if args.cmd == "roundtrip":
        return _cmd_roundtrip(args.paths)
    if args.cmd == "to-json":
        return _cmd_to_json(args.paths)
    if args.cmd == "to-l5x":
        return _cmd_to_l5x(args.paths)
    if args.cmd == "diff":
        return _cmd_diff(args.a, args.b)
    return 1


def _cmd_validate(paths: list[Path]) -> int:
    failures = 0
    for path in paths:
        ok, reason = validate_l5x(path.read_bytes())
        if ok:
            print(f"OK       {path}")
        else:
            failures += 1
            print(f"INVALID  {path}: {reason}", file=sys.stderr)
    return 1 if failures else 0


def _cmd_roundtrip(paths: list[Path]) -> int:
    failures = 0
    for path in paths:
        original = path.read_bytes()
        a = l5x_to_dict(original)
        b = l5x_to_dict(dict_to_l5x(a))
        if a == b:
            print(f"OK       {path}")
        else:
            failures += 1
            print(f"DIFFER   {path}", file=sys.stderr)
    return 1 if failures else 0


def _cmd_to_json(paths: list[Path]) -> int:
    failures = 0
    for path in paths:
        json_path = path.with_suffix(path.suffix + ".json")
        try:
            convert_l5x_file_to_json(path, json_path)
            print(f"WROTE    {json_path}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAILED   {path}: {exc}", file=sys.stderr)
    return 1 if failures else 0


def _cmd_to_l5x(paths: list[Path]) -> int:
    failures = 0
    for path in paths:
        # Strip a trailing ".json" if present; otherwise reuse the path with .L5X.
        if path.suffix == ".json":
            target = path.with_suffix("")
            if target.suffix == "":
                target = target.with_suffix(".L5X")
        else:
            target = path.with_suffix(".L5X")
        try:
            convert_json_file_to_l5x(path, target)
            print(f"WROTE    {target}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAILED   {path}: {exc}", file=sys.stderr)
    return 1 if failures else 0


def _cmd_diff(a: Path, b: Path) -> int:
    payload_a = read_json(a) if a.suffix == ".json" else l5x_to_dict(a.read_bytes())
    payload_b = read_json(b) if b.suffix == ".json" else l5x_to_dict(b.read_bytes())
    entries = l5x_diff(payload_a, payload_b)
    for entry in entries:
        if entry.op == "added":
            print(f"+ {entry.path}: {entry.after!r}")
        elif entry.op == "removed":
            print(f"- {entry.path}: {entry.before!r}")
        else:
            print(f"~ {entry.path}: {entry.before!r} → {entry.after!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
