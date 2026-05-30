"""Supervisory control runtime.

Ties the PLC I/O, link-health watchdog, and MPC controller together into the
event-gated state machine documented in :mod:`plc_workflows_mpc.supervisor`.
Mirrors the proven mpc-supervisor reference, with two adaptations:

* control decisions are emitted as record-dicts through a ``record_sink``
  callback (the adapter wraps them into ``ContextualRecord`` for forge);
* the runtime is thread-safe — :meth:`stop` is signalled via a
  ``threading.Event`` so :meth:`run_forever` exits cleanly from another thread.

The PLC retains full authority: hard SP clamps and the heartbeat watchdog live
on the PLC side; the soft ``sp_min``/``sp_max`` here is *defence in depth*.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import numpy as np

from plc_workflows_mpc.apc.mpc.base import MpcController
from plc_workflows_mpc.config import TagMap
from plc_workflows_mpc.plc_io.base import CycleInputs, PlcLink
from plc_workflows_mpc.supervisor.base import LinkHealth, Mode, SupervisorService

log = logging.getLogger("plc_workflows_mpc.supervisor")

RecordSink = Callable[[dict[str, Any]], None]


@dataclass(frozen=True)
class SupervisorConfig:
    """Runtime knobs for the supervisor (timing, safety, identity)."""

    control_period_s: float = 5.0
    poll_s: float = 0.25
    dry_run: bool = True
    sp_min: float | None = None
    sp_max: float | None = None
    equipment_id: str = "UNKNOWN_EQ"
    loop_id: str = "UNKNOWN_LOOP"
    controller_type: str = "MPC"
    area: str | None = None
    site: str | None = None
    operating_mode: str | None = "PRODUCTION"


@dataclass
class SupervisorRunner(SupervisorService):
    """Concrete IDLE/ARMING/RUNNING supervisor.

    Construct with the runtime config, tag map, PLC link, MPC controller, link
    health, and an optional ``record_sink`` callback that receives one dict per
    decision (control move, mode change, fault).
    """

    config: SupervisorConfig
    tags: TagMap
    plc_link: PlcLink
    controller: MpcController
    health: LinkHealth
    record_sink: RecordSink = field(default=lambda _: None)

    def __post_init__(self) -> None:
        self._mode = Mode.IDLE
        self._stop = threading.Event()
        self._next_solve = 0.0
        self._out_hb = 0
        self._io_fail = 0

    # ── Public API (SupervisorService) ─────────────────────────

    @property
    def mode(self) -> Mode:
        return self._mode

    def step(self, now: float) -> None:
        cfg = self.config
        inp = self.plc_link.read_cycle()

        if not inp.io_ok:
            self._io_fail += 1
            reconnect_every = max(1, int(2.0 / cfg.poll_s))
            if self._io_fail % reconnect_every == 0:
                self.plc_link.reconnect()
        else:
            self._io_fail = 0

        healthy, stable = self.health.update(inp.plc_heartbeat, inp.io_ok, now)

        # 1. heartbeat lost while controlling → immediate revert to local PID
        if self._mode is Mode.RUNNING and not healthy:
            self._drop_active("heartbeat unhealthy")
            self._to(Mode.ARMING, "awaiting stable heartbeat before re-enable")

        # 2. event cleared → release and go idle
        if inp.io_ok and not inp.enabled:
            if self._mode is Mode.RUNNING:
                self._drop_active("enable cleared by PLC")
            self._to(Mode.IDLE, "enable cleared")

        # 3. event set while idle → begin hold-off
        if inp.io_ok and inp.enabled and self._mode is Mode.IDLE:
            self._to(Mode.ARMING, "enable set; starting re-arm hold-off")

        # 4. hold-off satisfied → arm bumplessly and take the loop
        if self._mode is Mode.ARMING and inp.enabled and stable:
            cv = np.array(inp.cv, dtype=float)
            mv = np.array([inp.mv_feedback], dtype=float)
            self.controller.reset(y_meas=cv, u_active=mv)
            if not cfg.dry_run:
                self.plc_link.write(self.tags.active, True)
            self._to(Mode.RUNNING, "hold-off satisfied; control armed")
            self._next_solve = now

        # 5. control action at the MPC cadence
        if self._mode is Mode.RUNNING and now >= self._next_solve:
            self._control_action(inp)
            self._next_solve = now + cfg.control_period_s

        # 6. outgoing heartbeat
        self._out_hb = (self._out_hb + 1) % 1_000_000
        if not cfg.dry_run:
            self.plc_link.write(self.tags.heartbeat_out, self._out_hb)

    def run_forever(self) -> None:
        cfg = self.config
        log.info(
            "supervisor start: control_period=%.1fs poll=%.2fs dry_run=%s",
            cfg.control_period_s,
            cfg.poll_s,
            cfg.dry_run,
        )
        try:
            while not self._stop.is_set():
                self.step(time.monotonic())
                # Use Event.wait so stop() interrupts the sleep promptly.
                if self._stop.wait(cfg.poll_s):
                    break
        finally:
            if self._mode is Mode.RUNNING:
                self._drop_active("service shutdown")
            self.plc_link.close()
            log.info("supervisor stopped")

    def stop(self) -> None:
        self._stop.set()

    # ── Internals ──────────────────────────────────────────────

    def _control_action(self, inp: CycleInputs) -> None:
        cfg = self.config
        cv = np.array(inp.cv, dtype=float)
        dv = np.array(inp.dv, dtype=float)
        sp_target = np.array([inp.setpoint_target], dtype=float)

        self.controller.estimate(cv, dv)
        u = self.controller.solve(sp_target, dv)
        self.controller.commit(u)

        sp_raw = float(u[0])
        sp_clamped = self._apply_soft_clamp(sp_raw)

        record = self._build_record(
            event_type="control_move",
            value=sp_clamped,
            cv_value=float(cv[0]) if cv.size else None,
            dv_value=float(dv[0]) if dv.size else None,
            sp_target=float(sp_target[0]),
            mv_feedback=inp.mv_feedback,
            extra={"sp_raw": sp_raw, "sp_clamped": sp_clamped},
        )
        self._emit(record)

        log.info(
            "CV=%s SP_target=%.3f DV=%s -> MV_SP=%.3f%s",
            f"{cv[0]:.3f}" if cv.size else "—",
            sp_target[0],
            f"{dv[0]:.3f}" if dv.size else "—",
            sp_clamped,
            "  [DRY-RUN]" if cfg.dry_run else "",
        )

        if not cfg.dry_run:
            self.plc_link.write(self.tags.mv_setpoint, sp_clamped)

    def _apply_soft_clamp(self, sp: float) -> float:
        cfg = self.config
        if cfg.sp_min is not None and sp < cfg.sp_min:
            return cfg.sp_min
        if cfg.sp_max is not None and sp > cfg.sp_max:
            return cfg.sp_max
        return sp

    def _to(self, new: Mode, reason: str) -> None:
        if new is self._mode:
            return
        log.info("mode %s -> %s (%s)", self._mode.name, new.name, reason)
        old = self._mode
        self._mode = new
        self._emit(
            self._build_record(
                event_type="mode_change",
                value=new.name,
                extra={"from": old.name, "to": new.name, "reason": reason},
            )
        )

    def _drop_active(self, reason: str) -> None:
        if not self.config.dry_run:
            self.plc_link.write(self.tags.active, False)
        log.warning("released MPC control: %s", reason)
        self._emit(
            self._build_record(
                event_type="control_released",
                value=False,
                extra={"reason": reason},
            )
        )

    def _build_record(
        self,
        *,
        event_type: str,
        value: Any,
        cv_value: float | None = None,
        dv_value: float | None = None,
        sp_target: float | None = None,
        mv_feedback: float | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        cfg = self.config
        rec: dict[str, Any] = {
            "equipment_id": cfg.equipment_id,
            "area": cfg.area,
            "site": cfg.site,
            "operating_mode": cfg.operating_mode,
            "loop_id": cfg.loop_id,
            "controller_type": cfg.controller_type,
            "cv_tag": self.tags.cv[0] if self.tags.cv else None,
            "mv_tag": self.tags.mv_setpoint,
            "dv_tag": self.tags.dv[0] if self.tags.dv else None,
            "sp_tag": self.tags.setpoint_target,
            "event_type": event_type,
            "value": value,
            "timestamp": datetime.now(tz=UTC).isoformat(),
        }
        if cv_value is not None:
            rec["cv_value"] = cv_value
        if dv_value is not None:
            rec["dv_value"] = dv_value
        if sp_target is not None:
            rec["sp_target"] = sp_target
        if mv_feedback is not None:
            rec["mv_feedback"] = mv_feedback
        if extra:
            rec.update(extra)
        return rec

    def _emit(self, record: dict[str, Any]) -> None:
        try:
            self.record_sink(record)
        except Exception:  # noqa: BLE001
            log.exception("record_sink raised; dropping record")


__all__ = ["SupervisorConfig", "SupervisorRunner"]
