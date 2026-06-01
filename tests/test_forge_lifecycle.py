"""Forge-integration tests — control-plane happy path.

Drives the full lifecycle (``register → configure → start → stream → stop``)
through :class:`FakeForgeHub`, asserting both sides of the contract: the hub
servicer transitions session state correctly, and the spoke adapter mirrors
it.
"""

from __future__ import annotations

from forge.core.models.adapter import AdapterState

from harness import FakeForgeHub
from plc_workflows_mpc import PlcWorkflowsMpcAdapter


def _sample_record(*, loop_id: str = "TIC-101", value: float = 1.0) -> dict:
    return {
        "equipment_id": "FERM-003",
        "loop_id": loop_id,
        "controller_type": "MPC",
        "mv_tag": "TIC-101.OUT",
        "event_type": "control_move",
        "value": value,
        "timestamp": "2026-06-01T12:00:00Z",
    }


async def test_register_returns_session_id_and_creates_session():
    async with FakeForgeHub.over(PlcWorkflowsMpcAdapter()) as hub:
        session_id = await hub.register()
        assert session_id == "session-plc-workflows-mpc-0"
        session = hub.session()
        assert session.adapter_id == "plc-workflows-mpc"
        assert session.state == AdapterState.REGISTERED
        assert session.configured is False
        assert session.started is False


async def test_configure_transitions_hub_to_connecting():
    async with FakeForgeHub.over(PlcWorkflowsMpcAdapter()) as hub:
        await hub.register()
        await hub.configure({"plc_path": None})
        session = hub.session()
        assert session.configured is True
        assert session.state == AdapterState.CONNECTING
        # The adapter applied the same params on its side.
        assert hub.adapter.state == AdapterState.REGISTERED


async def test_start_transitions_both_sides_to_healthy():
    async with FakeForgeHub.over(PlcWorkflowsMpcAdapter()) as hub:
        await hub.run_lifecycle({"plc_path": None})
        assert hub.session().state == AdapterState.HEALTHY
        assert hub.session().started is True
        assert hub.adapter.state == AdapterState.HEALTHY


async def test_stop_transitions_both_sides_to_stopped():
    async with FakeForgeHub.over(PlcWorkflowsMpcAdapter()) as hub:
        await hub.run_lifecycle()
        await hub.stop()
        assert hub.session().state == AdapterState.STOPPED
        assert hub.session().started is False
        assert hub.adapter.state == AdapterState.STOPPED


async def test_stream_once_returns_count_and_hub_receives_records():
    async with FakeForgeHub.over(PlcWorkflowsMpcAdapter()) as hub:
        await hub.run_lifecycle()
        hub.adapter.inject_records([_sample_record(value=1.0), _sample_record(value=2.0)])
        sent = await hub.stream_once()
        assert sent == 2
        assert hub.total_sent == 2
        received = await hub.received_records()
        assert len(received) == 2
        assert [r.value.raw for r in received] == [1.0, 2.0]


async def test_multiple_stream_cycles_accumulate():
    async with FakeForgeHub.over(PlcWorkflowsMpcAdapter()) as hub:
        await hub.run_lifecycle()
        for cycle in range(3):
            hub.adapter.inject_records([_sample_record(value=float(cycle))])
            sent = await hub.stream_once()
            assert sent == 1
        assert hub.session().records_received == 3
        assert hub.total_sent == 3


async def test_stream_once_with_empty_queue_is_a_noop():
    async with FakeForgeHub.over(PlcWorkflowsMpcAdapter()) as hub:
        await hub.run_lifecycle()
        # No inject — adapter's queue is empty.
        sent = await hub.stream_once()
        assert sent == 0
        assert hub.session().records_received == 0


async def test_hub_health_rpc_returns_running_state():
    async with FakeForgeHub.over(PlcWorkflowsMpcAdapter()) as hub:
        await hub.run_lifecycle()
        health = await hub.hub_health()
        assert health["adapter_id"] == "plc-workflows-mpc"
        # state is proto-encoded by forge's serializer; just confirm presence.
        assert "state" in health


async def test_run_lifecycle_factory_method_drives_three_calls():
    """Smoke-test that ``run_lifecycle`` actually executes the three RPCs."""
    async with FakeForgeHub.over(PlcWorkflowsMpcAdapter()) as hub:
        session_id = await hub.run_lifecycle({"plc_path": None})
        session = hub.session()
        assert session.session_id == session_id
        assert session.configured is True
        assert session.started is True
        assert session.state == AdapterState.HEALTHY


async def test_records_drain_clears_hub_queue():
    async with FakeForgeHub.over(PlcWorkflowsMpcAdapter()) as hub:
        await hub.run_lifecycle()
        hub.adapter.inject_records([_sample_record()])
        await hub.stream_once()
        first = await hub.received_records()
        # Second drain after no new records should be empty.
        second = await hub.received_records()
        assert len(first) == 1
        assert second == []
