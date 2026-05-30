"""Module entry-point: ``python -m plc_workflows_mpc.sdlc <command> [paths…]``."""

from __future__ import annotations

from plc_workflows_mpc.sdlc.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
