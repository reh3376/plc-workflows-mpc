"""Tests for the record builder."""

from datetime import UTC, datetime

from forge.core.models.contextual_record import QualityCode

from plc_workflows_mpc.context import build_record_context
from plc_workflows_mpc.record_builder import build_contextual_record

_RAW = {
    "equipment_id": "FERM-003",
    "loop_id": "TIC-101",
    "controller_type": "MPC",
    "mv_tag": "TIC-101.OUT",
    "event_type": "control_move",
    "value": 42.5,
    "engineering_units": "%",
    "timestamp": "2026-05-29T12:00:00Z",
}


def _build(raw):
    return build_contextual_record(
        raw_event=raw,
        context=build_record_context(raw),
        adapter_id="plc-workflows-mpc",
        adapter_version="0.1.0",
    )


def test_full_record_assembly():
    record = _build(_RAW)
    assert record.source.adapter_id == "plc-workflows-mpc"
    assert record.source.system == "plc-workflows-mpc"
    assert record.source.tag_path == "TIC-101.OUT"
    assert record.value.raw == 42.5
    assert record.value.data_type == "float64"
    assert record.value.engineering_units == "%"
    assert record.value.quality == QualityCode.GOOD
    assert record.lineage.schema_ref == "forge://schemas/plc-workflows-mpc/v0.1.0"
    assert record.context.equipment_id == "FERM-003"
    assert record.context.extra["loop_id"] == "TIC-101"


def test_timestamp_parsed_to_aware_datetime():
    record = _build(_RAW)
    assert record.timestamp.source_time == datetime(2026, 5, 29, 12, 0, tzinfo=UTC)


def test_tag_path_falls_back_to_loop_and_event():
    raw = {"loop_id": "FIC-9", "event_type": "model_identified", "value": 1}
    record = _build(raw)
    assert record.source.tag_path == "FIC-9.model_identified"


def test_error_flag_marks_quality_bad():
    raw = {**_RAW, "error": "solver_infeasible"}
    record = _build(raw)
    assert record.value.quality == QualityCode.BAD


def test_data_type_inference():
    assert _build({**_RAW, "value": True}).value.data_type == "bool"
    assert _build({**_RAW, "value": 7}).value.data_type == "int64"
    assert _build({**_RAW, "value": "open"}).value.data_type == "string"
