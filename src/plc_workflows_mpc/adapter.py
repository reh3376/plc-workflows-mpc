"""PLC Workflows MPC adapter — the forge spoke entry point.

This spoke is an **advanced process control (APC) controller** on the forge
hub-and-spoke platform. Its role in the data flow:

    subscribe  → receive process variables (PV/CV/SP) from the hub
                 (fed by the OT / historian spokes)
    compute    → MPC / APC controllers and the optimization layer decide moves
    write      → push setpoints / MV moves back to the PLC layer via the hub
    collect    → emit every controller decision and optimization result as a
                 governed ContextualRecord (an auditable OT control trail)
    discover   → enumerate the control loops / controllers this spoke manages

The PLC link itself follows the supervisory pattern proven in the mpc-supervisor
reference: Rockwell Logix PLCs are addressed over EtherNet/IP via ``pycomm3``
(see :mod:`plc_workflows_mpc.plc_io`), driven by an IDLE/ARMING/RUNNING state
machine (:mod:`plc_workflows_mpc.supervisor`) with the PLC retaining full
authority (watchdog, permissive, hard setpoint clamps).

Phase 0 implements the full lifecycle and all four capability hooks in
**inject-only** mode (mirroring forge's reference modules): records are supplied
via ``inject_records()`` for unit testing, while live EtherNet/IP and hub gRPC
I/O are deferred to later phases. This keeps the skeleton fully testable without
hardware or a running hub.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from forge.adapters.base.interface import (
    AdapterBase,
    DiscoveryProvider,
    SubscriptionProvider,
    WritableAdapter,
)
from forge.core.models.adapter import (
    AdapterCapabilities,
    AdapterHealth,
    AdapterManifest,
    AdapterState,
    AdapterTier,
    ConnectionParam,
    DataContract,
)
from forge.core.models.contextual_record import ContextualRecord

from plc_workflows_mpc.config import PlcWorkflowsMpcConfig
from plc_workflows_mpc.context import build_record_context
from plc_workflows_mpc.record_builder import build_contextual_record

logger = logging.getLogger(__name__)

_MANIFEST_PATH = Path(__file__).parent / "manifest.json"


def _load_manifest() -> AdapterManifest:
    """Load and validate the adapter manifest from ``manifest.json``."""
    raw = json.loads(_MANIFEST_PATH.read_text())
    return AdapterManifest(
        adapter_id=raw["adapter_id"],
        name=raw["name"],
        version=raw["version"],
        type=raw.get("type", "INGESTION"),
        protocol=raw["protocol"],
        tier=AdapterTier(raw["tier"]),
        capabilities=AdapterCapabilities(**raw.get("capabilities", {})),
        data_contract=DataContract(**raw["data_contract"]),
        health_check_interval_ms=raw.get("health_check_interval_ms", 5000),
        connection_params=[ConnectionParam(**p) for p in raw.get("connection_params", [])],
        auth_methods=raw.get("auth_methods", ["none"]),
        metadata=raw.get("metadata", {}),
    )


class PlcWorkflowsMpcAdapter(
    AdapterBase,
    WritableAdapter,
    SubscriptionProvider,
    DiscoveryProvider,
):
    """Forge APC controller spoke for PLC process control and optimization."""

    manifest: AdapterManifest = _load_manifest()

    def __init__(self) -> None:
        super().__init__()
        self._config: PlcWorkflowsMpcConfig | None = None
        self._pending_records: list[dict[str, Any]] = []
        self._subscriptions: dict[str, dict[str, Any]] = {}
        self._control_loops: list[dict[str, Any]] = []
        self._writes: list[dict[str, Any]] = []
        self._startup_time: datetime | None = None
        self._last_healthy: datetime | None = None

    # ── Lifecycle ──────────────────────────────────────────────

    async def configure(self, params: dict[str, Any]) -> None:
        """Validate connection parameters. Opens no connections."""
        self._config = PlcWorkflowsMpcConfig(**params)
        self._state = AdapterState.REGISTERED

    async def start(self) -> None:
        """Begin operation. Phase 0 is inject-only; no live I/O yet."""
        if self._config is None:
            raise RuntimeError("Adapter not configured — call configure() first")
        self._state = AdapterState.CONNECTING
        # Phase 2 will open the hub gRPC channel + optional EtherNet/IP link here.
        self._state = AdapterState.HEALTHY
        self._startup_time = datetime.now(tz=UTC)
        self._last_healthy = self._startup_time
        logger.info("plc-workflows-mpc adapter started (phase 0: inject-only)")

    async def stop(self) -> None:
        """Graceful shutdown."""
        self._pending_records.clear()
        self._subscriptions.clear()
        self._state = AdapterState.STOPPED
        logger.info("plc-workflows-mpc adapter stopped")

    async def health(self) -> AdapterHealth:
        """Report current health and counters."""
        uptime = 0.0
        if self._startup_time is not None:
            uptime = (datetime.now(tz=UTC) - self._startup_time).total_seconds()
        return AdapterHealth(
            adapter_id=self.adapter_id,
            state=self._state,
            last_check=datetime.now(tz=UTC),
            last_healthy=self._last_healthy,
            records_collected=self._records_collected,
            records_failed=self._records_failed,
            uptime_seconds=uptime,
        )

    # ── Collection (AdapterBase) ───────────────────────────────

    async def collect(self) -> AsyncIterator[ContextualRecord]:
        """Yield controller decisions / diagnostics as ContextualRecords."""
        while self._pending_records:
            raw_event = self._pending_records.pop(0)
            context = build_record_context(raw_event)
            record = build_contextual_record(
                raw_event=raw_event,
                context=context,
                adapter_id=self.adapter_id,
                adapter_version=self.manifest.version,
            )
            self._records_collected += 1
            yield record

    # ── Write-back (WritableAdapter) ───────────────────────────

    async def write(self, tag_path: str, value: Any, *, confirm: bool = True) -> bool:
        """Write a setpoint / MV move back to the PLC layer.

        Phase 0 records the intended write and reports success; Phase 2 wires
        this to the hub Write RPC (or direct EtherNet/IP via pycomm3).
        """
        self._writes.append({"tag_path": tag_path, "value": value, "confirm": confirm})
        logger.info(
            "plc-workflows-mpc queued write: %s = %r (confirm=%s)", tag_path, value, confirm
        )
        return True

    # ── Subscription (SubscriptionProvider) ────────────────────

    async def subscribe(self, tags: list[str], callback: Any) -> str:
        """Subscribe to PV/CV/SP value changes on the listed tags."""
        subscription_id = str(uuid4())
        self._subscriptions[subscription_id] = {"tags": list(tags), "callback": callback}
        logger.info("plc-workflows-mpc subscribed to %d tags (id=%s)", len(tags), subscription_id)
        return subscription_id

    async def unsubscribe(self, subscription_id: str) -> None:
        """Cancel an active subscription."""
        self._subscriptions.pop(subscription_id, None)
        logger.info("plc-workflows-mpc unsubscribed (id=%s)", subscription_id)

    # ── Discovery (DiscoveryProvider) ──────────────────────────

    async def discover(self) -> list[dict[str, Any]]:
        """Enumerate the control loops / controllers this spoke manages."""
        return [
            {
                "tag_path": loop.get("loop_id", "unknown"),
                "data_type": loop.get("controller_type", "unknown"),
                "description": loop.get("description", ""),
                "engineering_units": loop.get("engineering_units", ""),
            }
            for loop in self._control_loops
        ]

    # ── Testing / injection support ────────────────────────────

    def inject_records(self, raw_records: list[dict[str, Any]]) -> None:
        """Inject raw control events for testing (Phase 0)."""
        self._pending_records.extend(raw_records)

    def register_control_loops(self, loops: list[dict[str, Any]]) -> None:
        """Register control loops surfaced by ``discover()`` (Phase 0)."""
        self._control_loops.extend(loops)
