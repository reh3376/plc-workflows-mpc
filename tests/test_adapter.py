"""Tests for the PlcWorkflowsMpcAdapter lifecycle and capabilities."""

import pytest
from forge.core.models.adapter import AdapterState, AdapterTier

from plc_workflows_mpc import PlcWorkflowsMpcAdapter

_RAW_RECORDS = [
    {
        "equipment_id": "FERM-003",
        "loop_id": "TIC-101",
        "controller_type": "MPC",
        "mv_tag": "TIC-101.OUT",
        "event_type": "control_move",
        "value": 42.5,
        "timestamp": "2026-05-29T12:00:00Z",
    },
    {
        "equipment_id": "FERM-004",
        "loop_id": "FIC-201",
        "controller_type": "PID",
        "mv_tag": "FIC-201.OUT",
        "event_type": "control_move",
        "value": 17.0,
        "timestamp": "2026-05-29T12:00:01Z",
    },
]


@pytest.fixture
def adapter():
    return PlcWorkflowsMpcAdapter()


def test_manifest_identity(adapter):
    assert adapter.adapter_id == "plc-workflows-mpc"
    assert adapter.manifest.tier == AdapterTier.OT
    assert adapter.manifest.protocol == "ethernet_ip"
    caps = adapter.manifest.capabilities
    assert caps.read and caps.write and caps.subscribe and caps.discover
    assert caps.backfill is False


async def test_lifecycle_transitions(adapter):
    assert adapter.state == AdapterState.REGISTERED
    await adapter.configure({"forge_hub_endpoint": "grpc://hub:50051"})
    assert adapter.state == AdapterState.REGISTERED
    await adapter.start()
    assert adapter.state == AdapterState.HEALTHY
    health = await adapter.health()
    assert health.state == AdapterState.HEALTHY
    assert health.adapter_id == "plc-workflows-mpc"
    await adapter.stop()
    assert adapter.state == AdapterState.STOPPED


async def test_start_without_configure_raises(adapter):
    with pytest.raises(RuntimeError):
        await adapter.start()


async def test_inject_and_collect(adapter):
    await adapter.configure({})
    await adapter.start()
    adapter.inject_records(_RAW_RECORDS)
    records = [r async for r in adapter.collect()]
    assert len(records) == 2
    assert records[0].context.equipment_id == "FERM-003"
    assert records[0].source.tag_path == "TIC-101.OUT"
    health = await adapter.health()
    assert health.records_collected == 2


async def test_collected_records_pass_validation(adapter):
    await adapter.configure({})
    await adapter.start()
    adapter.inject_records(_RAW_RECORDS)
    async for record in adapter.collect():
        assert await adapter.validate_record(record) is True


async def test_write_records_intent(adapter):
    await adapter.configure({})
    await adapter.start()
    assert await adapter.write("TIC-101.SP", 75.0) is True


async def test_subscribe_and_unsubscribe(adapter):
    await adapter.configure({})
    await adapter.start()
    sub_id = await adapter.subscribe(["TIC-101.PV", "TIC-101.SP"], callback=lambda *_: None)
    assert isinstance(sub_id, str) and sub_id
    await adapter.unsubscribe(sub_id)


async def test_discover_lists_registered_loops(adapter):
    await adapter.configure({})
    await adapter.start()
    adapter.register_control_loops(
        [{"loop_id": "TIC-101", "controller_type": "MPC", "description": "Temp loop"}]
    )
    discovered = await adapter.discover()
    assert discovered == [
        {
            "tag_path": "TIC-101",
            "data_type": "MPC",
            "description": "Temp loop",
            "engineering_units": "",
        }
    ]
