"""FakeForgeHub — assemble forge's in-memory test fakes around our adapter.

This is the centerpiece of the integration harness. It hides the wiring of
three forge components into one async context-manager so test scenarios stay
readable::

    async with FakeForgeHub.over(PlcWorkflowsMpcAdapter()) as hub:
        await hub.run_lifecycle()
        hub.adapter.inject_records([{"equipment_id": "X", "loop_id": "Y", ...}])
        sent = await hub.stream_once()
        received = await hub.received_records()
        assert sent == 1 and len(received) == 1

The harness goes through exactly the same serialization path the real hub
will use (`pydantic_to_proto` on send, `proto_to_pydantic` on receive) and
the same control-plane RPCs (`Register`, `Configure`, `Start`, `Stop`,
`Health`), so behavior changes that break the wire contract surface here.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from typing import Any

from forge.core.models.contextual_record import ContextualRecord
from forge.transport.hub_server import AdapterSession, InMemoryServicer
from forge.transport.spoke_client import InMemoryChannel
from forge.transport.transport_adapter import GrpcTransportAdapter

from plc_workflows_mpc import PlcWorkflowsMpcAdapter


@dataclass
class FakeForgeHub:
    """One-call wiring of forge's in-memory test fakes around our adapter."""

    adapter: PlcWorkflowsMpcAdapter
    servicer: InMemoryServicer = field(default_factory=InMemoryServicer)
    channel: InMemoryChannel = field(init=False)
    transport: GrpcTransportAdapter = field(init=False)
    session_id: str | None = field(default=None, init=False)
    _entered: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        self.channel = InMemoryChannel(self.servicer)
        self.transport = GrpcTransportAdapter(adapter=self.adapter, channel=self.channel)

    # ── Construction ───────────────────────────────────────────

    @classmethod
    def over(
        cls,
        adapter: PlcWorkflowsMpcAdapter,
        *,
        servicer: InMemoryServicer | None = None,
    ) -> FakeForgeHub:
        """Construct a harness around an existing adapter, optionally with a
        custom (subclassed) servicer."""
        return cls(adapter=adapter, servicer=servicer or InMemoryServicer())

    # ── Async context-manager ─────────────────────────────────

    async def __aenter__(self) -> FakeForgeHub:
        self._entered = True
        return self

    async def __aexit__(self, *_: Any) -> None:
        # Best-effort tear-down: stop the transport if started, then close.
        if self.session_id is not None and self.session().started:
            with contextlib.suppress(Exception):
                await self.transport.stop()
        with contextlib.suppress(Exception):
            await self.transport.close()
        self._entered = False

    # ── Control-plane drivers ─────────────────────────────────

    async def register(self) -> str:
        """Register the adapter; capture and return the assigned ``session_id``."""
        self.session_id = await self.transport.register()
        return self.session_id

    async def configure(self, params: dict[str, Any] | None = None) -> None:
        """Configure the adapter on both the hub side and the spoke side."""
        await self.transport.configure(dict(params or {}))

    async def start(self) -> None:
        """Start the adapter on both sides."""
        await self.transport.start()

    async def stop(self) -> int:
        """Stop the adapter; returns the records-flushed count from the hub."""
        flushed = await self.transport.stop()
        return flushed

    async def run_lifecycle(self, params: dict[str, Any] | None = None) -> str:
        """Drive register → configure → start; return ``session_id``."""
        session_id = await self.register()
        await self.configure(params)
        await self.start()
        return session_id

    # ── Data-plane drivers ────────────────────────────────────

    async def stream_once(self) -> int:
        """Drain the adapter's ``collect()`` once and stream to the hub."""
        return await self.transport.collect_and_stream()

    # ── Inspection helpers ────────────────────────────────────

    async def received_records(self) -> list[ContextualRecord]:
        """All records the hub-side servicer has queued for our session."""
        if self.session_id is None:
            return []
        return await self.servicer.drain_records(self.session_id)

    def session(self) -> AdapterSession:
        """The hub-side :class:`AdapterSession` for our adapter."""
        if self.session_id is None:
            raise RuntimeError("not registered yet — call register() / run_lifecycle()")
        return self.servicer._sessions[self.session_id]

    @property
    def total_sent(self) -> int:
        """Cumulative count of records the spoke has streamed to the hub."""
        return self.transport.total_records_sent

    async def hub_health(self) -> dict[str, Any]:
        """Round-trip the hub's Health RPC."""
        return await self.transport.health()


__all__ = ["FakeForgeHub"]
