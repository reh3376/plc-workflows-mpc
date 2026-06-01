# Commissioning — live-hub smoke procedure

This procedure is the bridge between the in-memory integration harness
(verified automatically in CI via `tests/test_forge_*.py`) and a real customer
deployment. It exercises the **actual gRPC wire path** to a running forge hub
and gives you a fast, scripted pass/fail signal before you point the spoke at
production data.

## When to run it

1. After every meaningful change to `src/plc_workflows_mpc/adapter.py`,
   `manifest.json`, or `specs/plc-workflows-mpc.facts.json` — anything that
   could shift the wire contract.
2. As the first step of customer commissioning, before plugging in a real PLC.
3. Whenever a new forge hub release lands — the wire compatibility check is
   cheap and the alternative (silent serialization drift) is expensive.

## What it does

`scripts/forge_smoke.py` drives the full forge AdapterService lifecycle:

1. opens a real `grpc.aio` channel to the hub endpoint
2. `Register` — sends the manifest, expects a `session_id`
3. `Configure` — sends the connection params
4. `Start` — transitions the hub-side session to `HEALTHY`
5. streams **one** `ContextualRecord` via `Ingest` (skippable with `--no-stream`)
6. `Stop` — graceful shutdown

Exit code `0` ⇒ every step passed; `1` ⇒ something failed (the log tells you what).

## Prerequisite — a running forge hub

You need a forge hub reachable over gRPC. Three options, lightest first.

### Option A — in-process `GrpcServer` (lowest setup cost)

Useful for verifying the spoke alone without booting any of forge's data
stores. Effectively what the bonus pytest `tests/test_forge_live_grpc.py`
does — start a `GrpcServer(InMemoryServicer)` in one terminal and point the
smoke at it from another:

```bash
# In one terminal — boot a bare hub gRPC servicer
PYTHONPATH=/path/to/forge/src python -c "
import asyncio
from forge.transport.grpc_server import GrpcServer
from forge.transport.hub_server import InMemoryServicer

async def main():
    server = GrpcServer(InMemoryServicer(), port=50051, host='127.0.0.1')
    await server.start()
    print('hub up on 127.0.0.1:50051')
    await server.wait_for_termination()

asyncio.run(main())
"
```

```bash
# In another terminal — run the smoke
PYTHONPATH=/path/to/forge/src .venv/bin/python scripts/forge_smoke.py
```

### Option B — forge's full docker-compose stack

For end-to-end verification against the real hub with all its dependencies
(PostgreSQL, TimescaleDB, Neo4j, Redis, Kafka, MinIO, RabbitMQ):

```bash
cd /Users/reh3376/forge
docker compose -f deploy/docker/docker-compose.yml up -d
# wait ~30–60s for the stack to come up
```

The hub's gRPC port is **50051** by default. Then run the smoke:

```bash
cd /Users/reh3376/plc-workflows-mpc
PYTHONPATH=/Users/reh3376/forge/src .venv/bin/python scripts/forge_smoke.py
```

Shut the stack down when you're done:

```bash
cd /Users/reh3376/forge && docker compose -f deploy/docker/docker-compose.yml down
```

### Option C — remote / customer hub

```bash
PYTHONPATH=/path/to/forge/src .venv/bin/python scripts/forge_smoke.py \
    --hub-endpoint forge.example.com:50051
```

## Expected output on success

```
=== forge ↔ spoke live smoke ===
hub endpoint: 127.0.0.1:50051
plc_path:     (none — hub-mediated)
[1/6] connecting gRPC channel...
      ✓ connected
[2/6] registering adapter manifest with hub...
      ✓ registered (session=session-plc-workflows-mpc-0, manifest=plc-workflows-mpc)
[3/6] configuring adapter...
      ✓ configured
[4/6] starting adapter...
      ✓ started
[5/6] streaming one ContextualRecord to the hub...
      ✓ streamed 1 record(s) (total sent: 1)
[6/6] stopping adapter...
      ✓ stopped (records_flushed=1)
=== SMOKE PASSED ===
```

## Common failures

| What you see | Most likely cause | Where to look |
|---|---|---|
| `grpc.aio.AioRpcError ... StatusCode.UNAVAILABLE` | No hub at that endpoint, or wrong port | `docker compose ps` / firewall / `--hub-endpoint` |
| `Registration rejected: …` | Manifest doesn't match the hub's FACTS schema | `specs/plc-workflows-mpc.facts.json`; align with the hub's expected schema |
| `TypeError: bad argument type for built-in operation` on configure | A `None` value in the params dict (proto `map<string, string>` rejects None) | Make sure every value in `transport.configure(params)` is a real string |
| Smoke hangs in `[1/6] connecting` | Hub responding slowly or proto stubs version mismatch | Compare `grpcio` / `protobuf` versions on both sides |
| `[5/6] streamed 0 records` | Adapter queue was empty before stream (the inject-only path is correct in the smoke script — this means an internal regression) | Re-run the unit tests (`pytest tests/test_forge_*.py`) |

## What the smoke does NOT verify

- the spoke's behavior against a *real* PLC — that's a separate commissioning step using `dry_run=True` first;
- governance side-effects (FACTS validation, storage routing) — those live on the hub side;
- multi-session / concurrent-spoke behavior — out of scope for the smoke;
- error-recovery scenarios (channel reset, hub restart) — those have unit-test coverage in `tests/test_forge_error_paths.py`.

## After the smoke passes

1. Switch the spoke to live PLC mode (`plc_path` populated, `dry_run=True`).
2. Use `python -m plc_workflows_mpc.sdlc validate plc/*.L5X` to verify the PLC-side artifacts.
3. Run the supervisor in dry-run against the customer's controller for one full re-arm window (~30 s).
4. Drop `dry_run=False` only after the operator has confirmed they can interrupt control via `Operator_Override`.
