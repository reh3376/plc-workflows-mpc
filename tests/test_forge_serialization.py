"""Forge-integration tests — Pydantic ↔ proto round-trip.

When the real hub receives ``Register`` it runs the manifest through
``proto_to_pydantic`` and stores it as an :class:`AdapterManifest`. When it
receives ``Collect`` it runs each streamed :class:`ContextualRecord` through
the same path. These tests pin down that every field we care about — manifest
identity + capabilities + connection params + metadata, and the
extra-fields-laden control records the spoke emits — survives that round-trip
without loss.
"""

from __future__ import annotations

import pytest
from forge.core.models.adapter import AdapterTier

from harness import FakeForgeHub
from plc_workflows_mpc import PlcWorkflowsMpcAdapter

# ── Manifest round-trip ----------------------------------------------------


async def test_manifest_identity_survives_round_trip():
    async with FakeForgeHub.over(PlcWorkflowsMpcAdapter()) as hub:
        await hub.register()
        m = hub.session().manifest
        assert m.adapter_id == "plc-workflows-mpc"
        assert m.name == "PLC Workflows MPC Adapter"
        assert m.version == "0.1.0"
        assert m.tier == AdapterTier.OT
        assert m.protocol == "ethernet_ip"
        assert m.type == "INGESTION"


async def test_manifest_capabilities_survive_round_trip():
    async with FakeForgeHub.over(PlcWorkflowsMpcAdapter()) as hub:
        await hub.register()
        caps = hub.session().manifest.capabilities
        assert caps.read is True
        assert caps.write is True
        assert caps.subscribe is True
        assert caps.discover is True
        assert caps.backfill is False


async def test_manifest_connection_params_survive_round_trip():
    async with FakeForgeHub.over(PlcWorkflowsMpcAdapter()) as hub:
        await hub.register()
        params = {p.name: p for p in hub.session().manifest.connection_params}
        # The manifest declares 9 connection params; every one must round-trip.
        expected = {
            "forge_hub_endpoint",
            "plc_path",
            "control_period_s",
            "rearm_holdoff_s",
            "heartbeat_timeout_s",
            "sp_min",
            "sp_max",
            "dry_run",
            "verify_ssl",
        }
        assert expected <= set(params.keys())
        assert params["forge_hub_endpoint"].required is True
        assert params["forge_hub_endpoint"].default == "grpc://localhost:50051"
        assert params["dry_run"].default == "true"


async def test_manifest_metadata_round_trip_preserves_custom_fields():
    async with FakeForgeHub.over(PlcWorkflowsMpcAdapter()) as hub:
        await hub.register()
        meta = hub.session().manifest.metadata
        assert meta["spoke"] == "plc-workflows-mpc"
        assert meta["role"] == "apc_supervisory_controller"
        assert meta["plc_platform"] == "rockwell_logix"
        assert meta["plc_transport"] == "ethernet_ip_pycomm3"
        assert meta["predecessor"] == "plc-gbt"
        # Pillars list must be intact and ordered (forge metadata is dict[Any]).
        assert list(meta["pillars"]) == [
            "forge_core_integration",
            "plc_sdlc",
            "advanced_process_control",
            "plant_wide_optimization",
        ]


async def test_manifest_data_contract_survives_round_trip():
    async with FakeForgeHub.over(PlcWorkflowsMpcAdapter()) as hub:
        await hub.register()
        dc = hub.session().manifest.data_contract
        assert dc.output_format == "contextual_record"
        assert dc.schema_ref == "forge://schemas/plc-workflows-mpc/v0.1.0"
        assert "equipment_id" in dc.context_fields
        assert "loop_id" in dc.context_fields


# ── Record round-trip -------------------------------------------------------


def _record(
    *,
    event_type: str,
    value: object,
    extra: dict[str, object] | None = None,
) -> dict:
    base = {
        "equipment_id": "FERM-003",
        "area": "Fermentation",
        "site": "Plant1",
        "operating_mode": "PRODUCTION",
        "loop_id": "TIC-101",
        "controller_type": "MPC",
        "mv_tag": "MPC_Temp_SP",
        "cv_tag": "Reactor_Temp",
        "dv_tag": "Feed_Flow",
        "sp_tag": "MPC_CV_Target",
        "event_type": event_type,
        "value": value,
        "timestamp": "2026-06-01T12:00:00Z",
    }
    if extra:
        base.update(extra)
    return base


async def _stream(records: list[dict]):
    async with FakeForgeHub.over(PlcWorkflowsMpcAdapter()) as hub:
        await hub.run_lifecycle()
        hub.adapter.inject_records(records)
        sent = await hub.stream_once()
        received = await hub.received_records()
        return sent, received


async def test_control_move_record_survives_round_trip():
    raw = _record(event_type="control_move", value=42.5)
    sent, received = await _stream([raw])
    assert sent == 1 and len(received) == 1
    rec = received[0]
    assert rec.source.adapter_id == "plc-workflows-mpc"
    assert rec.source.system == "plc-workflows-mpc"
    assert rec.source.tag_path == "MPC_Temp_SP"
    assert rec.context.equipment_id == "FERM-003"
    assert rec.context.area == "Fermentation"
    assert rec.context.site == "Plant1"
    assert rec.context.operating_mode == "PRODUCTION"
    assert rec.context.extra["loop_id"] == "TIC-101"
    assert rec.context.extra["controller_type"] == "MPC"
    assert rec.context.extra["cv_tag"] == "Reactor_Temp"
    assert rec.context.extra["dv_tag"] == "Feed_Flow"
    assert rec.value.raw == 42.5
    assert rec.lineage.schema_ref == "forge://schemas/plc-workflows-mpc/v0.1.0"
    assert rec.lineage.adapter_id == "plc-workflows-mpc"


async def test_mode_change_record_survives_round_trip():
    raw = _record(
        event_type="mode_change",
        value="RUNNING",
        extra={"from": "ARMING", "to": "RUNNING", "reason": "hold-off satisfied"},
    )
    _, received = await _stream([raw])
    rec = received[0]
    assert rec.context.extra["event_type"] == "mode_change"
    # Extra fields the supervisor emits land in context.extra after round-trip.
    assert rec.context.extra.get("from") == "ARMING"
    assert rec.context.extra.get("to") == "RUNNING"
    assert rec.context.extra.get("reason") == "hold-off satisfied"
    assert rec.value.raw == "RUNNING"


async def test_optimization_decision_record_survives_round_trip():
    raw = _record(
        event_type="optimization_decision",
        value=255.0,
        extra={
            "loop_id": "plant",
            "controller_type": "RTO",
            "objective_name": "proof_gallons",
            "objective_sense": "ObjectiveSense.MAXIMIZE",
            "setpoints": {"loop_a": 100.0, "loop_b": 50.0},
            "current_state": {"loop_a": 80.0, "loop_b": 30.0},
            "iterations": 5,
            "message": "Optimization terminated successfully",
        },
    )
    _, received = await _stream([raw])
    rec = received[0]
    assert rec.value.raw == 255.0
    extra = rec.context.extra
    assert extra["controller_type"] == "RTO"
    assert extra["objective_name"] == "proof_gallons"
    assert extra["setpoints"] == {"loop_a": 100.0, "loop_b": 50.0}
    assert extra["iterations"] == 5


async def test_record_quality_default_is_good():
    """RecordValue.quality is an enum; default GOOD must survive round-trip."""
    raw = _record(event_type="control_move", value=1.0)
    _, received = await _stream([raw])
    rec = received[0]
    assert rec.value.quality.value == "GOOD"


async def test_record_data_type_is_inferred_and_preserved():
    cases = [
        ("control_move", 1.5, "float64"),
        ("control_move", 1, "int64"),
        ("control_move", True, "bool"),
        ("mode_change", "IDLE", "string"),
    ]
    for event_type, value, expected_dt in cases:
        _, received = await _stream(
            [_record(event_type=event_type, value=value)]
        )
        assert received[0].value.data_type == expected_dt, (event_type, value)


async def test_multiple_records_arrive_in_order():
    payloads = [_record(event_type="control_move", value=float(i)) for i in range(5)]
    sent, received = await _stream(payloads)
    assert sent == 5
    assert [r.value.raw for r in received] == [0.0, 1.0, 2.0, 3.0, 4.0]


@pytest.mark.parametrize(
    "ev",
    ["control_move", "mode_change", "control_released", "optimization_fault"],
)
async def test_every_supervisor_event_type_survives_round_trip(ev: str):
    _, received = await _stream([_record(event_type=ev, value=1.0)])
    assert len(received) == 1
    assert received[0].context.extra["event_type"] == ev
