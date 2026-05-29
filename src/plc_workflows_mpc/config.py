"""Connection, timing, safety, and tag configuration for the spoke.

The control link follows the supervisory pattern proven in the mpc-supervisor
reference: a Rockwell Logix PLC is addressed over EtherNet/IP (``pycomm3``), the
PLC keeps full authority (PID, permissive, watchdog, hard setpoint clamps), and
this service only writes a *candidate* setpoint while permitted. Defaults are
safe: ``dry_run`` is on (read + solve, never write) for commissioning.

Maps to ``manifest.json`` ``connection_params`` (the hub validates raw params
against the manifest, then passes them to ``configure()``).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TagMap(BaseModel):
    """Logix tag names the service reads/writes. Override per deployment."""

    enable: str = Field(default="MPC_Enable", description="BOOL, PLC→us: grant control.")
    active: str = Field(default="MPC_Active", description="BOOL, us→PLC: we hold the loop.")
    heartbeat_out: str = Field(default="MPC_Heartbeat", description="DINT, us→PLC heartbeat.")
    heartbeat_in: str = Field(default="PLC_Heartbeat", description="DINT, PLC→us heartbeat.")
    mv_setpoint: str = Field(default="MPC_Temp_SP", description="REAL, us→PLC: candidate SP.")
    mv_feedback: str = Field(
        default="Reactor_Temp_SP_Active", description="REAL, PLC live SP (bumpless arm)."
    )
    setpoint_target: str = Field(default="MPC_CV_Target", description="REAL, operator CV target.")
    cv: tuple[str, ...] = Field(
        default=("Reactor_Temp",), description="Controlled/process variable tag(s)."
    )
    dv: tuple[str, ...] = Field(
        default=("Feed_Flow",), description="Measured disturbance variable tag(s)."
    )

    model_config = ConfigDict(frozen=True)


class PlcWorkflowsMpcConfig(BaseModel):
    """Validated connection / timing / safety configuration for the spoke."""

    forge_hub_endpoint: str = Field(
        default="grpc://localhost:50051",
        description="Forge hub gRPC endpoint the spoke registers with.",
    )
    plc_path: str | None = Field(
        default=None,
        description="Rockwell EtherNet/IP path 'ip[/slot]' (e.g. 192.168.1.10/1). "
        "None = hub-mediated only (no direct PLC link).",
    )
    control_period_s: float = Field(
        default=5.0, gt=0.0, le=3600.0, description="MPC control period (seconds)."
    )
    poll_s: float = Field(
        default=0.25, gt=0.0, le=60.0, description="Enable/heartbeat poll period (seconds)."
    )
    heartbeat_timeout_s: float = Field(
        default=2.0, gt=0.0, le=60.0, description="PLC heartbeat must advance within (seconds)."
    )
    rearm_holdoff_s: float = Field(
        default=30.0, ge=0.0, le=3600.0, description="Healthy time before (re)arming (seconds)."
    )
    sp_min: float | None = Field(default=None, description="Soft lower clamp on the written SP.")
    sp_max: float | None = Field(default=None, description="Soft upper clamp on the written SP.")
    dry_run: bool = Field(
        default=True, description="If True, read + solve but never write (commissioning)."
    )
    verify_ssl: bool = Field(default=True, description="Verify TLS for the hub connection.")
    tags: TagMap = Field(default_factory=TagMap)

    model_config = ConfigDict(frozen=True)

    @model_validator(mode="after")
    def _check_sp_band(self) -> PlcWorkflowsMpcConfig:
        if self.sp_min is not None and self.sp_max is not None and self.sp_min >= self.sp_max:
            raise ValueError("sp_min must be strictly less than sp_max")
        return self
