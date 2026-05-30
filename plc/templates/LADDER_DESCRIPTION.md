# Ladder logic — rung-by-rung equivalent of `MPC_Supervisor.st`

The supervisory interlock is supplied as Structured Text in `MPC_Supervisor.st`
because it is exact and portable. If your site standard is ladder, the same
logic maps to the rungs below. Put this in a **Periodic Task at 100 ms**. None
of this is scan-rate process control — it is the authority/permissive layer
around a regulatory PID loop that already exists in your program.

Convention: `XIC` = examine-if-closed (NO contact), `XIO` = examine-if-open
(NC contact), `OTE` = output energize, `TONR` = retentive timer on,
`MOV` / `CMP` = move / compare, `LIM` = limit test.

---

### Rung 1 — PLC heartbeat (prove the controller is alive to the PC)

```
|  [ADD  PLC_Heartbeat  1  PLC_Heartbeat]                                   |
|  --[GRT PLC_Heartbeat 1000000]----[MOV 0 PLC_Heartbeat]----               |
```

A free-running counter the MPC service reads. If it stops advancing the
service knows the link or the controller is dead.

### Rung 2 — Detect incoming MPC heartbeat change-of-state

```
|  --[NEQ MPC_Heartbeat MPC_Heartbeat_Last]--+--[MOV MPC_Heartbeat MPC_Heartbeat_Last]--|
|                                            +--[RES MPC_HB_Watchdog_T]----------------|
```

Whenever the service's heartbeat changes, reset the watchdog timer.

### Rung 3 — Service-alive watchdog

```
|  ------------------------------[TONR MPC_HB_Watchdog_T  PRE=2000ms]-------|
|  --[XIO MPC_HB_Watchdog_T.DN]----------------( ) MPC_Service_Alive--------|
```

The timer is continuously enabled; rung 2 keeps resetting it while the
heartbeat is healthy. If the heartbeat stalls for two seconds the timer
`.DN` sets and `MPC_Service_Alive` drops. A frozen counter from a dropped
EtherNet/IP connection triggers this identically — link loss and process
death give the same result.

### Rung 4 — Re-arm hold-off (mirror of the PC-side X seconds)

```
|  --[XIC MPC_Enable]--[XIC MPC_Service_Alive]--+--[TONR MPC_Rearm_T PRE=30000ms]--|
|                                               |                                  |
|  --[XIO (enable AND alive)]-------------------+--[RES MPC_Rearm_T]---------------|
|  --[XIC MPC_Rearm_T.DN]-----------------------------( ) MPC_Rearm_OK-------------|
```

Requires the service to be enabled *and* alive continuously for thirty
seconds before the loop may be handed over. Any interruption resets the
timer — this is the anti-flap guard that prevents control bouncing on and
off around an intermittent fault.

### Rung 5 — Master permissive

```
|  --[XIC MPC_Enable]--[XIC MPC_Active]--[XIC MPC_Service_Alive]--[XIC MPC_Rearm_OK]--[XIO Operator_Override]--( ) MPC_Permissive |
```

All five conditions must hold for the MPC to drive the loop. Drop any one
and the loop reverts on the next scan.

### Rung 6 — Setpoint selection with hard clamp

```
|  --[XIC MPC_Permissive]--+--[LIM MPC_SP_Min  MPC_Temp_SP  MPC_SP_Max]--[MOV MPC_Temp_SP Reactor_Temp_SP]--|
|                          +--[XIO in-band]--[GRT MPC_Temp_SP MPC_SP_Max]--[MOV MPC_SP_Max Reactor_Temp_SP]-|
|                          +--[XIO in-band]--[LES MPC_Temp_SP MPC_SP_Min]--[MOV MPC_SP_Min Reactor_Temp_SP]-|
|                                                                                                            |
|  --[XIO MPC_Permissive]----------------------------------[MOV Reactor_Temp_SP_Local Reactor_Temp_SP]------|
```

When permitted, the PID setpoint follows the clamped MPC value. Otherwise
it reverts to the local/operator fail-safe setpoint. **This rung is the
automatic revert to standard PID control.**

### Rung 7 — Publish live SP for bumpless arming

```
|  ------------------------------[MOV Reactor_Temp_SP  Reactor_Temp_SP_Active]--|
```

The service reads `Reactor_Temp_SP_Active` at the moment it arms so its
first move is incremental from the current setpoint — no bump.

### Existing rung (unchanged) — regulatory PID

Your existing PID / PIDE instruction continues to use `Reactor_Temp_SP` as
its setpoint and drives the actuator. The supervisory layer above only
ever changes *which value* lands in `Reactor_Temp_SP`; it never touches the
PID output or the valve. All loop integrity and scan-rate control stay in
the controller.

---

## Why the watchdog lives in the PLC, not the PC

The single most important design choice is that the controller does not
trust the PC to be alive. The service must keep changing `MPC_Heartbeat`,
and rungs 2–3 verify it. If the service crashes, hangs, or the network
drops, the heartbeat freezes, the watchdog fires, `MPC_Service_Alive`
drops, the permissive opens, and rung 6 reverts to local PID — all on a
deterministic 100 ms scan with no cooperation required from the PC. The
PC-side hold-off (rung 4's mirror) only governs how eagerly control is
*re-taken*; the controller alone guarantees it can be *given back* safely.
