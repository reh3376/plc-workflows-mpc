# Architecture

`plc-workflows-mpc` is a **Forge spoke module** that provides OT-side advanced
process control, PLC SDLC, and plant-wide optimization. This document describes
the spoke's role on the Forge platform, the supervisory control architecture for
linking MPC to Rockwell PLCs, the PLC-side contract, and the build-out roadmap.

## 1. Role on the Forge platform

Forge is a hub-and-spoke platform: a central hub collects, governs, and serves
data via small single-responsibility spoke modules that exchange `ContextualRecord`s
over gRPC. This spoke is the **advanced process control** spoke. Observability and
AI/ML analysis are explicitly **out of scope** — they belong to other spokes.

The spoke implements the Forge adapter contract (`AdapterBase` plus the
`WritableAdapter`, `SubscriptionProvider`, and `DiscoveryProvider` capability
mixins) and behaves as an **APC controller**:

| Capability | Direction | Purpose |
|-----------|-----------|---------|
| `subscribe` | hub → spoke | receive process variables (PV/CV/SP) from the OT/historian spokes |
| `write` | spoke → PLC | push computed setpoints / MV moves back to the control layer |
| `collect` | spoke → hub | emit every controller decision + optimization result as a governed record |
| `discover` | spoke → hub | enumerate the control loops / controllers managed |

## 2. The four pillars

1. **Forge core integration** — the adapter (`adapter.py`, `config.py`, `context.py`, `record_builder.py`, `manifest.json`) and the `specs/*.facts.json` governance contract.
2. **PLC SDLC** (`sdlc/`) — git-native PLC development: L5X/ACD ↔ text conversion and CI/CD pipelines for PLC code.
3. **Advanced process control** (`apc/`) — process model **identification**, control-strategy **selection** (PID/APC/MPC), and MPC **instantiation**.
4. **Plant-wide optimization** (`optimization/`) — a real-time optimization layer coordinating controllers toward a user-defined objective (e.g. *maximize proof gallons*).

## 3. Supervisory control architecture (MPC ↔ Rockwell Logix)

The control link is **supervisory / advisory**: the PLC keeps full authority and
the Python service can only influence the loop while explicitly permitted. This
is the only safe way to put a server-side optimizer in front of a regulatory loop.

```
            EtherNet/IP (TCP 44818, pycomm3)
   ┌──────────────────────────────────────────────┐
   │                                                ▼
┌──┴───────────────────┐   reads CV/DV/enable   ┌────────────────────────────┐
│  Logix PLC            │ ─────────────────────► │  plc-workflows-mpc service │
│  • regulatory PID     │                        │   estimate (Kalman)        │
│  • permissive + hard  │   writes MV setpoint   │   solve MPC (QP, OSQP)      │
│    SP clamps          │ ◄───────────────────── │   clamp + rate-limit        │
│  • heartbeat watchdog │   + heartbeat          │   IDLE/ARMING/RUNNING SM   │
│    → reverts to PID   │                        └────────────────────────────┘
└───────────────────────┘
```

**Division of responsibility (strict):**
- The **PLC** owns the PID loop, the actuator, the permissive, the watchdog, and
  the hard setpoint clamps — everything safety- and timing-critical, on a
  deterministic scan.
- The **service** is advisory: it computes a candidate setpoint and writes it to a
  tag the PID reads, only while the PLC grants permission. It never touches the
  actuator and never runs in the scan-critical path.

**Control state machine** (`supervisor/`):
- `IDLE` — enable bit clear; the service only pulses its heartbeat.
- `ARMING` — enable set, but the service waits until the PLC link has been
  continuously healthy for the re-arm hold-off (anti-flap guard) before taking the
  loop. On entry to `RUNNING` it initializes the controller to the live setpoint
  (**bumpless transfer**).
- `RUNNING` — the service owns the loop: estimate → solve → write at the control
  period. On any heartbeat/IO fault it drops control immediately and falls back to
  `ARMING`.

**Failure behavior:** because the PLC independently watchdogs the service heartbeat
and clamps every setpoint, a crashed/hung/disconnected service causes the PLC to
revert to local PID within ~2 s with no cooperation required. The service-side
hold-off only governs how cautiously control is handed back *out*.

## 4. The MPC / APC core (`apc/mpc/`)

A constrained **linear** MPC over a discrete state-space model
(`x⁺ = A·x + Bu·u + Bd·d`, `y = C·x`):

- **Receding-horizon QP** solved with **OSQP** — the cost matrix is factored once;
  only the linear term and rate bounds change per cycle (real-time friendly).
- **Measured-disturbance feedforward** via `Bd`/`Gd`: the optimizer pre-acts on
  disturbances it can measure, canceling them before the CV deviates.
- **Offset-free Kalman observer**: an augmented integrating output disturbance
  drives zero steady-state error under unmeasured loads and plant/model mismatch.
- Control-cycle API: `reset` (bumpless arm) → `estimate` → `solve` → `commit`.

The `A, Bu, Bd, C` model comes from **system identification** (Pillar 3,
`apc/identification/`); the controller code is the easy part — identifying and
validating the process model *is* the APC project.

## 5. PLC-side contract (Rockwell Logix tags)

The PLC program must expose these controller-scope tags (names are configurable
via `config.TagMap`; defaults shown). The PLC side also implements the watchdog,
permissive, and re-arm timers.

| Tag | Type | Written by | Purpose |
|-----|------|-----------|---------|
| `MPC_Enable` | BOOL | PLC event/sequence | Grants MPC control on the trigger event |
| `MPC_Active` | BOOL | service | Service confirms it holds the loop |
| `MPC_Heartbeat` | DINT | service | Incremented every poll; PLC watchdogs it |
| `PLC_Heartbeat` | DINT | PLC | Incremented every scan; service reads to confirm link |
| `MPC_Permissive` | BOOL | PLC | Master gate; MPC may drive only when TRUE |
| `Operator_Override` | BOOL | HMI | Forces local PID regardless of MPC state |
| `MPC_Temp_SP` (MV) | REAL | service | Candidate setpoint computed by the MPC |
| `Reactor_Temp_SP` | REAL | PLC | Setpoint actually used by the regulatory PID |
| `Reactor_Temp_SP_Local` | REAL | operator/recipe | Fail-safe local setpoint when MPC not permitted |
| `Reactor_Temp_SP_Active` | REAL | PLC | Mirror of live PID SP; read for bumpless arm |
| `MPC_CV_Target` (SP) | REAL | operator/recipe | Target the MPC drives the CV toward |
| `MPC_SP_Min` / `MPC_SP_Max` | REAL | engineering | Hard clamps on any accepted setpoint |
| `Reactor_Temp` (CV) | REAL | instrument | Controlled/process variable regulated |
| `Feed_Flow` (DV) | REAL | instrument | Measured disturbance fed forward |

> The reference PLC-side artifacts (Structured Text routine, ladder equivalent,
> tag CSV) for this contract live at `~/Documents/dailylog/plc-mpc/mpc-supervisor/plc`.
> Pillar 2 (PLC SDLC) will ship generalized, version-controlled templates of these.

## 6. Package map

```
plc_workflows_mpc/
  adapter.py, config.py, context.py, record_builder.py, manifest.json   # Forge contract
  apc/identification/   process model ID (FOPDT/SOPDT/state-space)
  apc/selection/        control-strategy recommendation (PID/APC/MPC)
  apc/mpc/              MPC formulation + controller (PlantModel, OSQP)
  optimization/         plant-wide RTO toward a user objective
  sdlc/                 PLC git workflows / CI-CD / format conversion
  supervisor/           IDLE/ARMING/RUNNING control state machine + link health
  plc_io/               Rockwell EtherNet/IP link (pycomm3)
```

## 7. Roadmap

| Phase | Pillar | Scope |
|-------|--------|-------|
| **0** *(done)* | Forge core | Adapter contract, manifest, FACTS spec, interfaces, tests, CI — inject-only skeleton. |
| **1** *(done)* | APC | FOPDT/SOPDT identification (NLS, BIC selection), step detection, PID/APC/MPC recommendation. |
| **2** | APC | MPC instantiation (OSQP), supervisory state machine, live EtherNet/IP (pycomm3) + hub I/O. |
| **3** | SDLC | Git-native L5X/ACD↔text workflows + CI/CD pipeline templates + PLC-side tag/interlock templates. |
| **4** | Optimization | Plant-wide RTO coordinating controllers toward user-defined objectives. |
