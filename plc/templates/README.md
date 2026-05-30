# PLC-side integration templates

These are the **Logix-controller-side** artifacts that complete the supervisory
contract between the Python `plc-workflows-mpc` spoke (which runs on a server)
and the regulatory PID loop on a Rockwell controller. They are templates: copy
the files you want into your Studio 5000 project, rename the per-loop tags to
match your convention, and call the routine from a 100 ms Periodic Task.

| File | Purpose |
|------|---------|
| [`TAGS.csv`](TAGS.csv) | Controller-scope tag list (data types + descriptions) |
| [`MPC_Supervisor.st`](MPC_Supervisor.st) | Supervisory interlock routine (Structured Text) |
| [`LADDER_DESCRIPTION.md`](LADDER_DESCRIPTION.md) | Rung-by-rung ladder equivalent of the ST routine |

## What this contract is

The Python spoke is **advisory**: it computes a candidate setpoint and writes
it to `MPC_Temp_SP`. The PLC is **authoritative**: it owns the regulatory PID,
the actuator, the operator override, the heartbeat watchdog, and the hard
setpoint clamps. The supervisor routine here is the gatekeeper that decides,
*on every scan*, whether `Reactor_Temp_SP` follows the MPC's value or reverts
to the local fail-safe.

The full safety guarantee is: **the PLC reverts to local PID within ~2 s of any
failure — service crash, network drop, frozen heartbeat, operator override,
out-of-range candidate setpoint — with no cooperation from the PC.** The
hold-off on rung 4 only governs how cautiously control is *re-taken*; the
revert is unconditional and deterministic.

## How to apply

1. **Add the tags**: import `TAGS.csv` into your controller scope, or create
   them by hand from the table.
2. **Add the routine**: import `MPC_Supervisor.st` as a Structured Text routine
   (or build the rungs in `LADDER_DESCRIPTION.md` if your standard is ladder),
   and call it from a Periodic Task set to **100 ms**.
3. **Repoint your PID**: change your existing regulatory PID/PIDE
   instruction's `.SP` to read `Reactor_Temp_SP`. Do not change the PID
   itself — its tuning, its limits, and its actuator linkage stay exactly as
   they are.
4. **Wire your event**: drive `MPC_Enable` from your phase / sequence / event
   logic (e.g. *phase active AND in-envelope AND operator-armed*).
5. **Set the safety band**: configure `MPC_SP_Min` and `MPC_SP_Max` to the
   range you would let *any* operator-entered setpoint take. The spoke's
   `sp_min` / `sp_max` are soft clamps applied in software — these are the
   hard clamps the PLC enforces unconditionally.
6. **Set the fail-safe**: set `Reactor_Temp_SP_Local` to whatever value the
   loop should run at when the MPC is not permitted. The operator / recipe
   layer can update it; the supervisor routine never writes it.

## Renaming for your loop

This template is named for a temperature loop (`Reactor_Temp` / `Reactor_Temp_SP`)
because that matches the spoke's default `TagMap`. To apply the template to a
different loop, rename these four tags consistently:

| Template name | Rename to your loop's |
|---------------|------------------------|
| `Reactor_Temp` | the process variable (CV / PV) tag |
| `Reactor_Temp_SP` | the PID setpoint that follows the MPC |
| `Reactor_Temp_SP_Local` | the fail-safe / operator setpoint |
| `Reactor_Temp_SP_Active` | the live SP mirror the service reads |

All tags prefixed `MPC_` are generic to the supervisor and should keep their
names — the Python spoke's default `TagMap` is keyed on them, so no override
is needed unless you also rename on the spoke side.

## Why both ST and ladder?

ST is exact, terse, and easier to diff and review; ladder is what many sites
standardize on for shop-floor maintainability. Use whichever your site
standard demands — the *behavior* is identical, and the supervisor on the PC
side cannot tell which form you used.
