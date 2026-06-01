# Project status — handoff for the next coding agent

> Self-contained snapshot. Read this first if you're picking the project back up.

| | |
|--|--|
| **Last updated** | 2026-06-01 |
| **Last commit on `main`** | *latest after Phase 5 commit — forge-core test harness + context.py pass-through fix* |
| **Phase complete** | Phase 4 of 4 — all four pillars; **Phase 5 (forge-core integration harness) now done too** |
| **Quality gates** | `ruff` ✓ • `mypy --strict` ✓ (33 source files) • `pytest` ✓ (180 passed, 1 unrelated warning) |
| **Branch model** | trunk on `main`, conventional commits, no open branches |

## Where we are

The four pillars described in the [README](../README.md) and [ARCHITECTURE](ARCHITECTURE.md) are all implemented as concrete, unit-tested code; the forge hub ↔ spoke wire contract is now verified end-to-end via an in-memory harness (`tests/harness/FakeForgeHub`). The full integration backlog item #3 ("end-to-end integration test") is **done**; backlog item #4 ("forge hub registration verification") is **partially done** — the wire contract is exercised in-memory; a live-hub smoke against `/Users/reh3376/forge`'s docker-compose stack remains.

| Pillar | Phase | Where it lives | Concrete classes |
|--------|-------|----------------|-------------------|
| forge_core integration | 0 | `src/plc_workflows_mpc/{adapter,config,context,record_builder,manifest.json}` | `PlcWorkflowsMpcAdapter` |
| Process identification + strategy selection | 1 | `src/plc_workflows_mpc/apc/{identification,selection}` | `LeastSquaresIdentifier`, `recommend_strategy` |
| MPC control + supervisor + EtherNet/IP | 2 | `src/plc_workflows_mpc/{apc/mpc,supervisor,plc_io}` | `LinearMpcController`, `SupervisorRunner`, `HeartbeatLinkHealth`, `LogixLink` |
| PLC SDLC tooling + templates | 3 | `src/plc_workflows_mpc/sdlc`, `plc/templates` | `l5x_to_dict`/`dict_to_l5x`, `generate_github_workflow`, ST/ladder/tag templates |
| Plant-wide optimization | 4 | `src/plc_workflows_mpc/optimization` | `ScipyOptimizer`, `PlantCoordinator` |

Inter-pillar communication is wired via **callbacks** (`record_sink`, `setpoint_publisher`, `state_provider`, `queue_record`), not by hard dependencies — every layer can be unit-tested in isolation and substituted with a fake. The flip side: there is **no single function** that builds the whole stack from a config; the customer / next agent has to wire the pieces. See "What's open" below.

## How to verify locally

```bash
# 1. Create a Python 3.12 venv and install the dev + apc extras.
uv venv --python 3.12
uv pip install -e /Users/reh3376/forge        # local editable forge (private repo)
uv pip install -e ".[apc,dev]"

# 2. Run the gates (forge is on PYTHONPATH because it's installed editable).
.venv/bin/ruff check src tests
.venv/bin/mypy src
.venv/bin/pytest -q
```

Expected: ruff `All checks passed!`, mypy `Success: no issues found in 33 source files`, pytest `141 passed`.

If you're verifying without installing forge (e.g. quick re-runs), the established pattern in this project's history is to drop the `-e ./forge` install and instead put forge on `PYTHONPATH` at command time:

```bash
PYTHONPATH=/Users/reh3376/forge/src .venv/bin/pytest -q
```

## What's open (next-step backlog, roughly prioritized)

### High priority — closes the integration gap

1. **`build_supervisor()` factory.** Today the customer has to manually construct `LogixLink`, `HeartbeatLinkHealth`, `instantiate_mpc`, and `SupervisorRunner` and wire the `record_sink` to the adapter. A one-call factory that takes a `PlcWorkflowsMpcConfig` + a `PlantModel` + `MpcConfig` + an adapter, and returns a ready-to-attach `SupervisorRunner`, removes the biggest first-customer hurdle. Live with the adapter in `src/plc_workflows_mpc/adapter.py` or a new `src/plc_workflows_mpc/runtime.py`.

2. **Multi-loop coordinator ↔ supervisor bridge.** The user's "maximize proof gallons across processes" requires multiple `SupervisorRunner`s (one per loop) coordinated by one `PlantCoordinator`. The mechanics: `PlantCoordinator.setpoint_publisher` receives `{loop_id: setpoint}` — each supervisor needs to read its own loop's value. Options:
   - publish setpoints into a shared `dict` that each supervisor reads from on its next cycle, replacing the PLC-read `setpoint_target` for that loop, **or**
   - have the coordinator write each setpoint to the corresponding Logix `MPC_CV_Target` tag via its own `PlcLink`.
   Pick one, implement it, write the integration test below.

3. **End-to-end integration test.** ✅ **DONE.** `tests/harness/FakeForgeHub` + the four `tests/test_forge_*.py` files exercise the full lifecycle (register → configure → start → stream → stop), the Pydantic ↔ proto round-trip for the manifest and every record variant the spoke emits (`control_move`, `mode_change`, `control_released`, `optimization_decision`, `optimization_fault`), the supervisor-driven live mode, and the error paths. The harness uses forge's own `InMemoryServicer` + `InMemoryChannel` + `GrpcTransportAdapter` so the same serialization path the live hub takes is on the wire. **Side-effect** of writing it: the harness surfaced a real bug where `src/plc_workflows_mpc/context.py` was dropping all rich payload fields (`from`/`to`/`reason` on `mode_change`, `objective_name`/`setpoints`/`iterations` on `optimization_decision`); fixed by making the context builder pass-through unknown fields into `RecordContext.extra`.

### Medium priority — readiness for first deployment

4. **Forge hub registration verification.** ⚠️ **PARTIAL.** The wire contract (manifest + record proto round-trip + RPC dispatch shape) is now verified in-memory via the harness above — `tests/test_forge_serialization.py` pins down every manifest field and every record variant. **Still open:** the live-hub smoke. Start the hub from `/Users/reh3376/forge` (see its `docker-compose.yml`), wrap `PlcWorkflowsMpcAdapter` in `forge.transport.GrpcTransportAdapter` against a real-gRPC `TransportChannel`, point it at `grpc://localhost:50051`, and verify the spoke registers and a single `Collect` stream completes. Update the FACTS spec if the hub rejects anything in production that the in-memory servicer accepted.

5. **Real-PLC commissioning smoke test.** Once an integrator has a Logix controller available, the procedure should be: import `plc/templates/TAGS.csv` + `MPC_Supervisor.st`, run the spoke with `dry_run=true` against the PLC for one cycle, confirm the heartbeat advances and records emit correctly, then flip `dry_run=false` and write a benign setpoint. Document the procedure as `docs/COMMISSIONING.md`.

6. **CI prerequisite.** `.github/workflows/ci.yml` checks out `reh3376/forge` using a `FORGE_REPO_TOKEN` secret. **The secret must be configured in the GitHub repo settings before CI can pass.** Until then, CI will fail at the forge-checkout step — expected, not a code regression.

### Lower priority — polish

7. **`examples/` directory** with a worked notebook that (a) generates synthetic step-test data, (b) identifies a FOPDT model, (c) picks a strategy, (d) instantiates the MPC, (e) runs a short closed-loop simulation, (f) builds an `OptimizationProblem` and solves it. Customer onboarding artifact.

8. **Architecture diagram** (`docs/architecture.svg` or PNG) showing the four pillars + data flow. Referenced from the ARCHITECTURE doc and README.

9. **PyPI / distribution decision.** Source-only via git (current default), private PyPI mirror, or release tarballs. Document the publish flow once decided.

10. **Dead-time SOPDT closed-loop test.** The `apc/mpc/realization.py` delay-buffer code handles dead time, but the closed-loop MPC tests in `tests/test_mpc_controller.py` only exercise zero-dead-time plants. Add a test that runs the controller on a SOPDT plant with `n_d > 0` delay states.

## Intentionally deferred (do **not** implement these without scope confirmation)

- **`.ACD` binary conversion.** Requires Studio 5000 or the external `plc-format-converter` (`/Users/reh3376/repos/plc-format-converter`). Document the bridge if you need it, but the L5X side is the right anchor.
- **Nonlinear / robust MPC.** `LinearMpcController` covers the common case; tackling NMPC pulls in `casadi` / `do-mpc` and a much bigger surface.
- **Asyncio-native runtime.** Current threading model (daemon thread + `threading.Event`) is faithful to the reference and unit-testable. An asyncio refactor is a *huge* change for no current win.
- **Observability + AI/ML analysis.** Out of scope by design — those belong to other forge spokes (see the project memory).

## Quick orientation map — where things live

```
plc-workflows-mpc/
├── README.md, docs/                         high-level docs + this STATUS
├── plc/templates/                           customer-facing PLC-side artifacts
├── pyproject.toml                           deps + ruff/mypy/pytest config
├── specs/plc-workflows-mpc.facts.json       forge governance contract
├── src/plc_workflows_mpc/
│   ├── adapter.py                           forge AdapterBase impl (live + inject-only)
│   ├── config.py                            Pydantic connection / timing / safety + TagMap
│   ├── context.py, record_builder.py        raw event → ContextualRecord
│   ├── manifest.json                        forge adapter manifest
│   ├── apc/                                 IDENTIFICATION + SELECTION + MPC
│   ├── optimization/                        PLANT-WIDE RTO
│   ├── plc_io/                              ROCKWELL ETHERNET/IP via pycomm3
│   ├── sdlc/                                L5X ↔ JSON + CLI + CI generator
│   └── supervisor/                          IDLE/ARMING/RUNNING state machine
└── tests/
    ├── fakes.py                             FakePlcLink, FakeMpcController, make_cycle
    ├── test_*.py                            141 tests organized one file per module
```

## Where to read first

If you're new to the codebase:
1. `README.md` — the why
2. `docs/ARCHITECTURE.md` — the architecture and supervisory control story
3. `src/plc_workflows_mpc/apc/mpc/controller.py` — the algorithmic heart
4. `src/plc_workflows_mpc/supervisor/service.py` — how everything is glued together at runtime

## Conventions

- **Conventional commits.** `feat(scope):` / `fix(scope):` / `docs(scope):` etc.
- **All commits must pass `ruff check src tests` + `mypy --strict src` + `pytest`.** No exceptions.
- **No new top-level dirs** without updating this STATUS doc, the README repo-layout block, and the ARCHITECTURE package map.
- **Soft imports** for runtime-only deps (`pycomm3`, `osqp`, …) so unit tests run without them.
