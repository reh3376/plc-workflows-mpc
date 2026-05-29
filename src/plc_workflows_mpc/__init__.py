"""plc-workflows-mpc — Forge spoke for OT advanced process control.

Four pillars:
  1. forge_core integration (this package's adapter)
  2. PLC SDLC                (:mod:`plc_workflows_mpc.sdlc`)
  3. advanced process control (:mod:`plc_workflows_mpc.apc`)
  4. plant-wide optimization  (:mod:`plc_workflows_mpc.optimization`)

Control runtime: :mod:`plc_workflows_mpc.supervisor` (IDLE/ARMING/RUNNING state
machine) drives :mod:`plc_workflows_mpc.plc_io` (Rockwell EtherNet/IP link).
"""

from __future__ import annotations

from plc_workflows_mpc.adapter import PlcWorkflowsMpcAdapter

__all__ = ["PlcWorkflowsMpcAdapter"]
__version__ = "0.1.0"
