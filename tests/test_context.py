"""Tests for the context builder."""

from plc_workflows_mpc.context import build_record_context


def test_maps_first_class_fields():
    ctx = build_record_context(
        {
            "equipment_id": "FERM-003",
            "area": "Fermentation",
            "site": "Plant1",
            "operating_mode": "PRODUCTION",
        }
    )
    assert ctx.equipment_id == "FERM-003"
    assert ctx.area == "Fermentation"
    assert ctx.site == "Plant1"
    assert ctx.operating_mode == "PRODUCTION"


def test_control_fields_go_to_extra():
    ctx = build_record_context(
        {
            "equipment_id": "FERM-003",
            "loop_id": "TIC-101",
            "controller_type": "MPC",
            "cv_tag": "Reactor_Temp",
            "mv_tag": "MPC_Temp_SP",
            "dv_tag": "Feed_Flow",
            "sp_tag": "MPC_CV_Target",
            "event_type": "control_move",
        }
    )
    assert ctx.extra["loop_id"] == "TIC-101"
    assert ctx.extra["controller_type"] == "MPC"
    assert ctx.extra["cv_tag"] == "Reactor_Temp"
    assert ctx.extra["dv_tag"] == "Feed_Flow"
    assert ctx.extra["event_type"] == "control_move"


def test_absent_fields_omitted_from_extra():
    ctx = build_record_context({"equipment_id": "X", "loop_id": "L1"})
    assert "cv_tag" not in ctx.extra
    assert ctx.area is None
