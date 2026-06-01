"""Forge-integration test — real gRPC wire path.

The other ``test_forge_*.py`` files use forge's ``InMemoryChannel`` which
covers the Pydantic ↔ proto-shape round-trip but not the actual binary
protobuf marshaling on TCP. This file plugs forge's ``GrpcChannel`` against
an in-process ``GrpcServer(InMemoryServicer)`` so we get real gRPC over a
loopback socket — same wire path the live hub will use.

Gated on ``grpcio`` being installed (the ``grpc`` optional extra and
``forge.transport.grpc_channel``). When ``grpcio`` is absent, the tests
skip — the in-memory harness still covers every other assertion.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

from plc_workflows_mpc import PlcWorkflowsMpcAdapter

# Skip the entire file if grpcio / forge's proto stubs aren't installed.
grpc = pytest.importorskip("grpc")
pytest.importorskip("google.protobuf")
GrpcChannel = pytest.importorskip("forge.transport.grpc_channel").GrpcChannel
GrpcServer = pytest.importorskip("forge.transport.grpc_server").GrpcServer
InMemoryServicer = pytest.importorskip("forge.transport.hub_server").InMemoryServicer
GrpcTransportAdapter = pytest.importorskip(
    "forge.transport.transport_adapter"
).GrpcTransportAdapter


@pytest_asyncio.fixture
async def live_hub() -> AsyncIterator[tuple[GrpcServer, InMemoryServicer, str]]:
    """Boot a ``GrpcServer(InMemoryServicer)`` on an OS-assigned free port.

    Yields ``(server, servicer, address)``; tears the server down on exit.
    """
    servicer = InMemoryServicer()
    server = GrpcServer(servicer, port=0, host="127.0.0.1")
    port = await server.start()
    try:
        yield server, servicer, f"127.0.0.1:{port}"
    finally:
        await server.stop(grace=0.5)


async def _connected_transport(address: str, adapter: PlcWorkflowsMpcAdapter):
    channel = GrpcChannel(address)
    await channel.connect()
    return channel, GrpcTransportAdapter(adapter=adapter, channel=channel)


def _sample_record(value: float = 1.0) -> dict:
    return {
        "equipment_id": "FERM-003",
        "loop_id": "TIC-101",
        "controller_type": "MPC",
        "mv_tag": "TIC-101.OUT",
        "event_type": "control_move",
        "value": value,
        "timestamp": "2026-06-01T12:00:00Z",
    }


# ── Tests -------------------------------------------------------------------


async def test_lifecycle_over_real_grpc(live_hub):
    """End-to-end control plane against a real gRPC server.

    Configure must use non-``None`` string values — protobuf
    ``map<string, string>`` rejects ``None``. The in-memory channel tolerates
    it because it skips proto serialization; the wire path doesn't.
    """
    _server, servicer, address = live_hub
    adapter = PlcWorkflowsMpcAdapter()
    channel, transport = await _connected_transport(address, adapter)
    try:
        session_id = await transport.register()
        assert session_id  # hub returned something
        # Empty params dict — the adapter's defaults take over.
        await transport.configure({})
        await transport.start()
        # Session is now tracked on the hub side.
        assert session_id in servicer._sessions  # noqa: SLF001
        assert servicer._sessions[session_id].started is True  # noqa: SLF001
        await transport.stop()
    finally:
        await channel.close()


async def test_stream_record_over_real_grpc(live_hub):
    _server, servicer, address = live_hub
    adapter = PlcWorkflowsMpcAdapter()
    channel, transport = await _connected_transport(address, adapter)
    try:
        session_id = await transport.register()
        await transport.configure({})
        await transport.start()
        adapter.inject_records([_sample_record(value=42.5)])
        sent = await transport.collect_and_stream()
        assert sent == 1
        received = await servicer.drain_records(session_id)
        assert len(received) == 1
        rec = received[0]
        # Real gRPC + real proto encoding preserved the shape.
        assert rec.source.adapter_id == "plc-workflows-mpc"
        assert rec.context.equipment_id == "FERM-003"
        assert rec.context.extra["loop_id"] == "TIC-101"
        assert rec.value.raw == 42.5
        await transport.stop()
    finally:
        await channel.close()


async def test_multiple_records_over_real_grpc(live_hub):
    _server, servicer, address = live_hub
    adapter = PlcWorkflowsMpcAdapter()
    channel, transport = await _connected_transport(address, adapter)
    try:
        session_id = await transport.register()
        await transport.configure({})
        await transport.start()
        adapter.inject_records([_sample_record(value=float(i)) for i in range(5)])
        sent = await transport.collect_and_stream()
        assert sent == 5
        received = await servicer.drain_records(session_id)
        assert [r.value.raw for r in received] == [0.0, 1.0, 2.0, 3.0, 4.0]
        await transport.stop()
    finally:
        await channel.close()


async def test_connection_refused_to_dead_endpoint():
    """Sanity: the channel surfaces gRPC errors when the hub isn't there."""
    channel = GrpcChannel("127.0.0.1:1")  # port 1 — guaranteed nothing listening
    await channel.connect()
    adapter = PlcWorkflowsMpcAdapter()
    transport = GrpcTransportAdapter(adapter=adapter, channel=channel)
    try:
        with pytest.raises(grpc.aio.AioRpcError):
            await transport.register()
    finally:
        await channel.close()
