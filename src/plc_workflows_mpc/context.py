"""Context builder — map raw control events into Forge ``RecordContext``.

This spoke emits controller decisions, model-identification results, and
optimization actions. Each carries OT control context: which control loop it
belongs to, the controller type, and the PV/MV/SP tags it acts on. Loop-level
fields that are not first-class on ``RecordContext`` are carried in ``extra``.
"""

from __future__ import annotations

from typing import Any

from forge.core.models.contextual_record import RecordContext

# Control-specific fields carried in RecordContext.extra.
# CV = controlled/process variable, MV = manipulated (written setpoint),
# DV = measured disturbance (fed forward), SP = operator/CV target.
_EXTRA_FIELDS = (
    "loop_id",
    "controller_type",
    "cv_tag",
    "mv_tag",
    "dv_tag",
    "sp_tag",
    "event_type",
)


def build_record_context(raw_event: dict[str, Any]) -> RecordContext:
    """Transform a raw control event into a ``RecordContext``.

    Args:
        raw_event: A control decision / diagnostic dict produced by the
            controller, model-identification, or optimization layers.

    Returns:
        A ``RecordContext`` with OT control metadata attached.
    """
    extra: dict[str, Any] = {}
    for field_name in _EXTRA_FIELDS:
        value = raw_event.get(field_name)
        if value is not None:
            extra[field_name] = value

    return RecordContext(
        equipment_id=raw_event.get("equipment_id"),
        area=raw_event.get("area"),
        site=raw_event.get("site"),
        operating_mode=raw_event.get("operating_mode"),
        extra=extra,
    )
