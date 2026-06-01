#!/usr/bin/env python3
"""Live-hub smoke test for the forge ↔ spoke wire contract.

Points the ``PlcWorkflowsMpcAdapter`` at any forge hub reachable over gRPC,
drives one full lifecycle (register → configure → start → stream one record →
stop), and reports pass / fail. Designed for the manual commissioning loop
described in ``docs/COMMISSIONING.md``: stand up a forge hub (locally via
docker-compose or remotely), point this script at it, watch a single
``ContextualRecord`` flow through the *real* gRPC wire path.

Differs from the in-memory harness (``tests/harness/FakeForgeHub``) in
exactly one place — the :class:`TransportChannel`. The harness uses forge's
``InMemoryChannel``; this script uses ``GrpcChannel`` over a real socket
with binary protobuf on the wire.

Usage::

    # Default: connect to localhost:50051
    python scripts/forge_smoke.py

    # Custom endpoint
    python scripts/forge_smoke.py --hub-endpoint forge.example.com:50051

    # Skip the streaming step (control-plane only)
    python scripts/forge_smoke.py --no-stream

Exit code 0 on full success, 1 on any failure. Both stdout and stderr are
designed to be readable from a tail -f during commissioning.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from typing import Any

from forge.transport.grpc_channel import GrpcChannel
from forge.transport.transport_adapter import GrpcTransportAdapter

from plc_workflows_mpc import PlcWorkflowsMpcAdapter

_LOG_FORMAT = "%(asctime)s  %(levelname)-5s  %(name)s  %(message)s"


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="forge_smoke",
        description="Live-hub smoke for plc-workflows-mpc ↔ forge over real gRPC.",
    )
    p.add_argument(
        "--hub-endpoint",
        default="localhost:50051",
        help="forge hub gRPC endpoint (host:port). Default: localhost:50051",
    )
    p.add_argument(
        "--plc-path",
        default=None,
        help="Optional EtherNet/IP path (e.g. 192.168.1.10/1). "
        "Default: hub-mediated only (no direct PLC link).",
    )
    p.add_argument(
        "--no-stream",
        action="store_true",
        help="Skip the data-plane test; only run the control-plane RPCs.",
    )
    p.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="DEBUG logging (includes forge transport internals).",
    )
    return p


def _sample_record() -> dict[str, Any]:
    """A single, well-formed control-move record for the smoke."""
    return {
        "equipment_id": "SMOKE_EQ",
        "area": "Smoke",
        "site": "Smoke",
        "operating_mode": "SMOKE",
        "loop_id": "SMOKE-LOOP-1",
        "controller_type": "MPC",
        "mv_tag": "SMOKE.MV",
        "cv_tag": "SMOKE.CV",
        "sp_tag": "SMOKE.SP",
        "event_type": "smoke_test",
        "value": 1.0,
        "timestamp": "2026-06-01T12:00:00Z",
    }


async def _run(args: argparse.Namespace) -> int:
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format=_LOG_FORMAT,
        stream=sys.stderr,
    )
    log = logging.getLogger("forge_smoke")

    log.info("=== forge ↔ spoke live smoke ===")
    log.info("hub endpoint: %s", args.hub_endpoint)
    log.info("plc_path:     %s", args.plc_path or "(none — hub-mediated)")

    channel = GrpcChannel(args.hub_endpoint)
    adapter = PlcWorkflowsMpcAdapter()

    try:
        log.info("[1/6] connecting gRPC channel...")
        await channel.connect()
        log.info("      ✓ connected")

        transport = GrpcTransportAdapter(adapter=adapter, channel=channel)

        log.info("[2/6] registering adapter manifest with hub...")
        session_id = await transport.register()
        log.info("      ✓ registered (session=%s, manifest=%s)", session_id, adapter.adapter_id)

        log.info("[3/6] configuring adapter...")
        params: dict[str, Any] = {}
        if args.plc_path:
            params["plc_path"] = args.plc_path
        await transport.configure(params)
        log.info("      ✓ configured")

        log.info("[4/6] starting adapter...")
        await transport.start()
        log.info("      ✓ started")

        if not args.no_stream:
            log.info("[5/6] streaming one ContextualRecord to the hub...")
            adapter.inject_records([_sample_record()])
            sent = await transport.collect_and_stream()
            if sent == 0:
                log.error("      ✗ stream completed but reported 0 records sent")
                return 1
            log.info(
                "      ✓ streamed %d record(s) (total sent: %d)",
                sent,
                transport.total_records_sent,
            )
        else:
            log.info("[5/6] streaming skipped (--no-stream)")

        log.info("[6/6] stopping adapter...")
        flushed = await transport.stop()
        log.info("      ✓ stopped (records_flushed=%d)", flushed)

        log.info("=== SMOKE PASSED ===")
        return 0

    except Exception as exc:  # noqa: BLE001 — top-level reporting
        log.exception("smoke FAILED: %s", exc)
        return 1
    finally:
        try:
            await channel.close()
        except Exception:  # noqa: BLE001
            log.debug("channel.close() raised during teardown", exc_info=True)


def main(argv: list[str] | None = None) -> int:
    args = _build_argparser().parse_args(argv)
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
