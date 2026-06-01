"""Forge-integration tests — guard rails / sad paths.

When the hub rejects a request, when the channel is closed, when the spoke
is asked to do something out of order: the adapter must stay in a sane
state and raise informative errors.
"""

from __future__ import annotations

from typing import Any

import pytest
from forge.transport.hub_server import AdapterSession, InMemoryServicer

from harness import FakeForgeHub
from plc_workflows_mpc import PlcWorkflowsMpcAdapter


class _RejectingRegisterServicer(InMemoryServicer):
    """Servicer that refuses every Register request — simulates an
    incompatible manifest, an unknown adapter_id, or a hub policy reject."""

    async def register(self, manifest_dict: dict[str, Any]) -> dict[str, Any]:
        return {"accepted": False, "message": "rejected by policy", "session_id": ""}


class _FailingConfigureServicer(InMemoryServicer):
    """Servicer that returns ``success=False`` on Configure."""

    async def configure(
        self, adapter_id: str, session_id: str, params: dict[str, str]
    ) -> dict[str, Any]:
        return {"success": False, "message": "bad params"}


async def test_register_rejection_raises_and_leaves_adapter_unregistered():
    adapter = PlcWorkflowsMpcAdapter()
    hub = FakeForgeHub.over(adapter, servicer=_RejectingRegisterServicer())
    async with hub:
        with pytest.raises(RuntimeError, match="rejected by policy"):
            await hub.register()
        # No session was created on the hub.
        assert hub.session_id is None
        assert hub.servicer._sessions == {}  # noqa: SLF001 — test inspection
        # The adapter never transitioned out of its initial REGISTERED state.
        # (REGISTERED is also the initial state from AdapterBase.__init__.)
        assert adapter.state.value == "REGISTERED"


async def test_configure_failure_surfaces_runtime_error():
    adapter = PlcWorkflowsMpcAdapter()
    hub = FakeForgeHub.over(adapter, servicer=_FailingConfigureServicer())
    async with hub:
        await hub.register()
        with pytest.raises(RuntimeError, match="bad params"):
            await hub.configure({"plc_path": "x"})
        # Hub-side session stays REGISTERED (not CONNECTING).
        assert hub.session().configured is False


async def test_configure_before_register_raises():
    adapter = PlcWorkflowsMpcAdapter()
    async with FakeForgeHub.over(adapter) as hub:
        with pytest.raises(RuntimeError, match="register"):
            await hub.configure({"plc_path": None})


async def test_start_before_register_raises():
    adapter = PlcWorkflowsMpcAdapter()
    async with FakeForgeHub.over(adapter) as hub:
        with pytest.raises(RuntimeError, match="register"):
            await hub.start()


async def test_stream_once_before_register_raises():
    adapter = PlcWorkflowsMpcAdapter()
    async with FakeForgeHub.over(adapter) as hub:
        with pytest.raises(RuntimeError, match="register"):
            await hub.stream_once()


async def test_stop_without_register_is_a_safe_noop():
    adapter = PlcWorkflowsMpcAdapter()
    async with FakeForgeHub.over(adapter) as hub:
        # Should not raise — there's nothing to stop.
        flushed = await hub.stop()
        assert flushed == 0


async def test_channel_closed_then_stream_once_raises():
    adapter = PlcWorkflowsMpcAdapter()
    hub = FakeForgeHub.over(adapter)
    async with hub:
        await hub.run_lifecycle()
        hub.adapter.inject_records(
            [
                {
                    "equipment_id": "X",
                    "loop_id": "L",
                    "event_type": "control_move",
                    "value": 1.0,
                }
            ]
        )
        await hub.transport.close()
        with pytest.raises(RuntimeError, match="closed"):
            await hub.stream_once()


async def test_adapter_session_records_received_is_zero_after_failed_register():
    """The hub servicer should not pre-allocate state for a rejected adapter."""
    adapter = PlcWorkflowsMpcAdapter()
    hub = FakeForgeHub.over(adapter, servicer=_RejectingRegisterServicer())
    async with hub:
        with pytest.raises(RuntimeError):
            await hub.register()
    assert hub.servicer._sessions == {}  # noqa: SLF001


async def test_custom_servicer_can_subclass_and_inspect():
    """Smoke that the harness accepts subclassed servicers — used in real tests
    to assert on FACTS validation or governance side-effects."""

    class _CountingServicer(InMemoryServicer):
        def __init__(self) -> None:
            super().__init__()
            self.register_calls = 0

        async def register(self, manifest_dict: dict[str, Any]) -> dict[str, Any]:
            self.register_calls += 1
            return await super().register(manifest_dict)

    servicer = _CountingServicer()
    async with FakeForgeHub.over(PlcWorkflowsMpcAdapter(), servicer=servicer) as hub:
        await hub.register()
        assert servicer.register_calls == 1
        # The session is still queryable through the harness.
        assert isinstance(hub.session(), AdapterSession)
