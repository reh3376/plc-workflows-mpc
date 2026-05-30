"""Smoke tests for the pillar / runtime interface packages.

Guards that the public contracts import and a few basic invariants hold.
"""

from plc_workflows_mpc.apc import ControlStrategy, MpcConfig, PlantModel
from plc_workflows_mpc.optimization import ObjectiveSense
from plc_workflows_mpc.plc_io import CycleInputs
from plc_workflows_mpc.supervisor import Mode


def test_supervisor_modes():
    assert {m.name for m in Mode} == {"IDLE", "ARMING", "RUNNING"}


def test_control_strategy_values():
    assert ControlStrategy.MPC == "MPC"
    assert {s.value for s in ControlStrategy} == {"PID", "APC", "MPC"}


def test_objective_sense_values():
    assert ObjectiveSense.MAXIMIZE == "maximize"


def test_cycle_inputs_defaults():
    ci = CycleInputs(enabled=True, plc_heartbeat=1, mv_feedback=0.0, setpoint_target=0.0)
    assert ci.io_ok is True
    assert ci.cv == [] and ci.dv == []


def test_mpc_config_defaults():
    cfg = MpcConfig()
    assert cfg.prediction_horizon == 30
    assert cfg.control_horizon == 8


def test_plant_model_is_exported():
    assert PlantModel.__name__ == "PlantModel"
