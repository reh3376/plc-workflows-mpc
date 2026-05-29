"""Smoke tests for the pillar / runtime interface packages.

These guard that the public contracts import and that the Phase-1+ entry points
are present as (not-yet-implemented) stubs.
"""

import pytest

from plc_workflows_mpc.apc import ControlStrategy, MpcConfig, PlantModel
from plc_workflows_mpc.apc.identification import identify_process_model
from plc_workflows_mpc.apc.mpc import instantiate_mpc
from plc_workflows_mpc.optimization import ObjectiveSense, build_optimizer
from plc_workflows_mpc.plc_io import CycleInputs, open_logix_link
from plc_workflows_mpc.sdlc import generate_pipeline
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


@pytest.mark.parametrize(
    "thunk",
    [
        lambda: identify_process_model(None),
        lambda: build_optimizer(None),  # type: ignore[arg-type]
        lambda: open_logix_link("192.168.1.10/1", None),
        lambda: generate_pipeline({}),
        lambda: instantiate_mpc(None, MpcConfig()),  # type: ignore[arg-type]
    ],
)
def test_phase_later_stubs_raise(thunk):
    with pytest.raises(NotImplementedError):
        thunk()


def test_plant_model_is_exported():
    assert PlantModel.__name__ == "PlantModel"
