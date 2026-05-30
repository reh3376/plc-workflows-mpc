# plc-workflows-mpc

A **Forge spoke module** for OT-side **advanced process control**, **PLC software-development lifecycle (SDLC)**, and **plant-wide optimization**.

> Status: **All four pillars shipped (Phases 0–4 complete).** The forge adapter (inject-only *and* live), FOPDT/SOPDT identification + PID/APC/MPC selection (Phase 1), OSQP-backed `LinearMpcController` + `SupervisorRunner` + `LogixLink` (Phase 2), L5X ↔ JSON SDLC tooling + GitHub Actions generator + PLC-side templates (Phase 3), and now the plant-wide RTO layer — SLSQP-backed `ScipyOptimizer` over `OptimizationProblem` (`PlantObjective`, `LoopVariable`, `Constraint`) plus the threaded periodic `PlantCoordinator` runtime that emits one decision record per cycle (Phase 4). 141 tests, ruff + mypy strict clean. See [Roadmap](#roadmap).

---

## Why this repo exists

This module is the generalized, customer-customizable successor to **[plc-gbt](https://github.com/reh3376/plc-gbt)**.

plc-gbt grew into a single large application that bundled an IDE, an AI/RAG assistant, observability, control-loop analysis, and PLC format conversion. That made it hard to reuse across customers and blurred the boundaries between concerns. The [Forge framework](https://github.com/reh3376/forge) takes the opposite approach: a central **hub** with many small, single-responsibility **spoke modules** that each do one thing well and exchange data through a common contract (the `ContextualRecord`).

`plc-workflows-mpc` is the spoke that owns **OT process control and PLC engineering workflows**. It is built to be a **general framework that is customized per customer with minor changes** rather than a bespoke one-off — the value a systems integrator can offer as a drop-in Forge module.

Concerns that plc-gbt also handled — **observability and AI/ML analysis** — are deliberately **out of scope** here; those belong to their own dedicated Forge spokes.

## Purpose

Bring industrial process control and PLC development up to modern software standards, and connect them to the Forge platform so that every control decision is governed, contextual, and auditable.

## Goals (the four pillars)

1. **Forge core integration** — implement the Forge adapter contract so the module registers with and exchanges data through the hub.
2. **PLC SDLC** — git workflows and CI/CD pipelines (plus L5X/ACD ↔ text conversion) that bring PLC development in line with standard software development.
3. **Advanced Process Control** — instantiate **MPC/APC** controllers, and analyze processes to **select the correct control algorithm** (PID / APC / MPC) for each loop.
4. **Plant-wide optimization** — a real-time optimization layer that coordinates all controllers toward a **user-defined objective** (e.g. *"maximize proof gallons produced"*) subject to process and business constraints.

## How it fits into Forge

This spoke is an **APC controller** on the hub-and-spoke platform:

```
  hub ──subscribe──▶  PV / CV / SP  ─┐
                                      ├─▶  APC / MPC + optimization  ──▶  control moves
  hub ◀──write──────  setpoints / MV ─┘                                   │
  hub ◀──collect────  governed ContextualRecords of every decision  ◀─────┘
  hub ◀──discover───  managed control loops / controllers
```

- **subscribe** — receive process variables from the hub (fed by the OT/historian spokes).
- **compute** — the `apc` and `optimization` packages decide the moves.
- **write** — push setpoints/MV moves back to the PLC layer.
- **collect** — emit every controller decision and optimization result as a `ContextualRecord` (an auditable OT control trail).
- **discover** — enumerate the control loops/controllers this spoke manages.

## Linking MPC to the PLC (supervisory / advisory)

For **Rockwell Logix** PLCs the control link follows a proven supervisory pattern (the PLC keeps full authority; this service is advisory):

- **Transport:** EtherNet/IP via [`pycomm3`](https://docs.pycomm3.dev/) — plain Logix tags, TCP 44818, explicit messaging. No RSLinx or Studio 5000 SDK at runtime.
- **Division of responsibility:** the **PLC** owns everything safety- and timing-critical (regulatory PID, actuator, permissive, watchdog, and **hard setpoint clamps**). The **service** only computes *which value lands in the PID setpoint*, and only while permitted.
- **Control runtime:** an `IDLE → ARMING → RUNNING` state machine (`supervisor/`) with a re-arm hold-off and **bumpless transfer** on takeover. The service pulses a heartbeat the PLC watchdogs; if the service dies, hangs, or loses the network, the PLC reverts to local PID within ~2 s — no cooperation required.
- **The MPC core** (`apc/mpc/`): a constrained linear QP (OSQP) over a discrete state-space model, with **measured-disturbance feedforward** (act before the CV deviates) and an **offset-free Kalman observer** (zero steady-state error under unmeasured load).
- **Commissioning:** `dry_run` is on by default — the service reads and solves but never writes until you explicitly enable it.

This structure is adapted from the reference at `~/Documents/dailylog/plc-mpc/mpc-supervisor`; see [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the PLC-side tag contract.

## Repository layout

```
src/plc_workflows_mpc/
  manifest.json        Forge adapter manifest (OT tier, ethernet_ip, read/write/subscribe/discover)
  adapter.py           PlcWorkflowsMpcAdapter — forge contract; inject-only or supervisor-driven
  config.py            Pydantic connection / timing / safety config + Logix tag map
  context.py           raw control event → RecordContext
  record_builder.py    → ContextualRecord
  apc/                 Pillar 3: identification + selection + mpc (LinearMpcController on OSQP) IMPLEMENTED
  optimization/        Pillar 4: plant-wide RTO — ScipyOptimizer (SLSQP) + PlantCoordinator — IMPLEMENTED
  sdlc/                Pillar 2: L5X ↔ JSON, validate, diff, CI generator + `python -m …sdlc` CLI — IMPLEMENTED
  supervisor/          Control runtime: IDLE/ARMING/RUNNING state machine — IMPLEMENTED
  plc_io/              Rockwell EtherNet/IP link via pycomm3 — IMPLEMENTED
plc/
  templates/           PLC-side artifacts (MPC_Supervisor.st, LADDER_DESCRIPTION.md, TAGS.csv, README.md)
specs/
  plc-workflows-mpc.facts.json   FACTS governance spec
tests/                 pytest suite
docs/ARCHITECTURE.md   the spoke's role, PLC-side contract + pillar roadmap
```

## Development

Requires **Python 3.12+** and [**uv**](https://docs.astral.sh/uv/). Forge is private and not on PyPI, so install it editable from a local checkout.

```bash
uv venv

# Install the forge platform (provides `forge-platform`):
uv pip install -e /path/to/forge          # local checkout (recommended for dev)
# …or, with repo access:
# uv pip install "forge-platform @ git+https://github.com/reh3376/forge.git"

# Install this package + dev tooling:
uv pip install -e ".[dev]"

# Quality gates:
uv run ruff check src tests
uv run mypy src
uv run pytest -v
```

The runtime control stack — the Rockwell EtherNet/IP link (`pycomm3`) and the QP solver (`osqp`) — lives in the optional `apc` extra and is needed once Pillar 3 implementation lands (Phase 2): `uv pip install -e ".[apc]"`.

## Roadmap

| Phase | Pillar | Scope |
|-------|--------|-------|
| **0** *(done)* | Forge core | Adapter contract, manifest, FACTS spec, tests, CI — inject-only skeleton. |
| **1** *(done)* | APC | FOPDT/SOPDT identification (NLS, BIC selection), step detection, PID/APC/MPC strategy recommendation. |
| **2** *(done)* | APC | OSQP-backed `LinearMpcController` (feedforward + offset-free observer), `SupervisorRunner` state machine, `LogixLink` over EtherNet/IP, live adapter wiring. |
| **3** *(done)* | SDLC | L5X ↔ JSON conversion (deterministic, round-trip), validation + structural diff, `python -m plc_workflows_mpc.sdlc` CLI, GitHub Actions workflow generator, PLC-side ST/ladder/tag templates. |
| **4** *(done)* | Optimization | `OptimizationProblem` (objective + variables + constraints), `ScipyOptimizer` (SLSQP), `PlantCoordinator` periodic runtime with state callback, setpoint publisher, and governed decision records. |

## License

Proprietary.
