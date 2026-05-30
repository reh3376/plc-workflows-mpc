(*
====================================================================
  MPC_Supervisor — PLC-side supervisory interlock (Structured Text)
====================================================================
  Platform : Allen-Bradley Logix (ControlLogix / CompactLogix), Studio 5000
  Purpose  : Owns the authority handshake with the external MPC service.
             The PLC GRANTS control via MPC_Enable; the external service
             CONFIRMS it holds control via MPC_Active and a live heartbeat.
             The regulatory PID setpoint follows the MPC value ONLY when
             all permissives are healthy; otherwise it reverts to a local
             fail-safe setpoint.

  Call this routine every scan from a Periodic Task (100 ms recommended).

  This routine is intentionally simple and self-contained. Every condition
  that can take the loop away from the MPC is evaluated here, in the PLC,
  on a deterministic scan — never delegated to the network or the PC.

  Per-loop renames: this template names the PV "Reactor_Temp" and the PID
  setpoint "Reactor_Temp_SP" (with _Local and _Active siblings). Rename
  those four tags to your loop's convention; everything prefixed "MPC_"
  is generic to the supervisor and should stay as-is so the Python
  spoke's default TagMap matches without overrides.
--------------------------------------------------------------------
  Tags used (see TAGS.csv for full data types / scopes).
  Constants:
    HB_WATCHDOG_PRE   := 2000    (ms) MPC heartbeat must change within this
    REARM_HOLDOFF_PRE := 30000   (ms) X seconds healthy before re-enable
====================================================================
*)

(* ---- 1. PLC heartbeat: prove the controller + link are alive ------------ *)
PLC_Heartbeat := PLC_Heartbeat + 1;
IF PLC_Heartbeat > 1000000 THEN
    PLC_Heartbeat := 0;
END_IF;

(* ---- 2. Service-alive watchdog on the INCOMING MPC heartbeat ------------ *)
(* Reset the watchdog whenever the service heartbeat advances. A frozen     *)
(* counter — from a dropped EtherNet/IP link, a hung process, a crash —     *)
(* lets the timer expire and we declare the service dead.                   *)
IF MPC_Heartbeat <> MPC_Heartbeat_Last THEN
    MPC_Heartbeat_Last := MPC_Heartbeat;
    MPC_HB_Watchdog_T.PRE := HB_WATCHDOG_PRE;
    MPC_HB_Watchdog_T.TT  := 0;
    MPC_HB_Watchdog_T.ACC := 0;
END_IF;
MPC_HB_Watchdog_T.TimerEnable := 1;
TONR(MPC_HB_Watchdog_T);
MPC_Service_Alive := NOT MPC_HB_Watchdog_T.DN;

(* ---- 3. Re-arm hold-off (mirror of the PC-side X seconds) --------------- *)
(* The service must be enabled AND alive continuously for REARM_HOLDOFF_PRE *)
(* before the loop may be handed over. Any interruption resets the timer.   *)
MPC_Rearm_T.PRE := REARM_HOLDOFF_PRE;
MPC_Rearm_T.TimerEnable := (MPC_Enable AND MPC_Service_Alive);
IF NOT MPC_Rearm_T.TimerEnable THEN
    MPC_Rearm_T.ACC := 0;
    MPC_Rearm_T.DN  := 0;
END_IF;
TONR(MPC_Rearm_T);
MPC_Rearm_OK := MPC_Rearm_T.DN;

(* ---- 4. Master permissive: may the MPC drive the regulatory loop? ------- *)
MPC_Permissive :=    MPC_Enable
                 AND MPC_Active
                 AND MPC_Service_Alive
                 AND MPC_Rearm_OK
                 AND NOT Operator_Override;

(* ---- 5. Setpoint selection + hard clamp --------------------------------- *)
(* When permitted, follow the clamped MPC setpoint. Otherwise revert to the *)
(* local fail-safe — this is the automatic fallback to standard PID.        *)
IF MPC_Permissive THEN
    IF MPC_Temp_SP < MPC_SP_Min THEN
        Reactor_Temp_SP := MPC_SP_Min;
    ELSIF MPC_Temp_SP > MPC_SP_Max THEN
        Reactor_Temp_SP := MPC_SP_Max;
    ELSE
        Reactor_Temp_SP := MPC_Temp_SP;
    END_IF;
ELSE
    Reactor_Temp_SP := Reactor_Temp_SP_Local;
END_IF;

(* ---- 6. Publish the live SP so the service can arm bumplessly ----------- *)
Reactor_Temp_SP_Active := Reactor_Temp_SP;

(* The regulatory PID instruction elsewhere uses Reactor_Temp_SP as its .SP. *)
(* Nothing above ever writes the PID output directly — loop integrity and    *)
(* all scan-rate control stay inside the PLC.                                *)
