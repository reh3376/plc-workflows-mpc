"""Tests for the connection / timing / safety configuration model."""

import pytest
from pydantic import ValidationError

from plc_workflows_mpc.config import PlcWorkflowsMpcConfig, TagMap


def test_defaults():
    cfg = PlcWorkflowsMpcConfig()
    assert cfg.forge_hub_endpoint == "grpc://localhost:50051"
    assert cfg.plc_path is None
    assert cfg.control_period_s == 5.0
    assert cfg.rearm_holdoff_s == 30.0
    assert cfg.heartbeat_timeout_s == 2.0
    assert cfg.dry_run is True  # safe default for commissioning
    assert isinstance(cfg.tags, TagMap)
    assert cfg.tags.enable == "MPC_Enable"
    assert cfg.tags.cv == ("Reactor_Temp",)


def test_accepts_valid_params():
    cfg = PlcWorkflowsMpcConfig(
        plc_path="192.168.1.10/1",
        control_period_s=1.0,
        sp_min=60.0,
        sp_max=90.0,
        dry_run=False,
    )
    assert cfg.plc_path == "192.168.1.10/1"
    assert cfg.dry_run is False
    assert (cfg.sp_min, cfg.sp_max) == (60.0, 90.0)


def test_is_frozen():
    cfg = PlcWorkflowsMpcConfig()
    with pytest.raises(ValidationError):
        cfg.control_period_s = 1.0  # type: ignore[misc]


def test_rejects_nonpositive_control_period():
    with pytest.raises(ValidationError):
        PlcWorkflowsMpcConfig(control_period_s=0.0)


def test_rejects_inverted_sp_band():
    with pytest.raises(ValidationError):
        PlcWorkflowsMpcConfig(sp_min=90.0, sp_max=60.0)


def test_ignores_unknown_params():
    # Hub-supplied params may include keys not on the model; they are ignored.
    cfg = PlcWorkflowsMpcConfig(some_future_param="x")
    assert cfg.plc_path is None
