"""Context builder — map raw control events into Forge ``RecordContext``.

This spoke emits controller decisions, model-identification results, and
optimization actions. Each carries OT control context: which control loop it
belongs to, the controller type, and the PV/MV/DV/SP tags it acts on, plus
event-specific fields (mode transitions name a ``from``/``to``/``reason``;
optimization decisions name an ``objective_name`` + ``setpoints``).

The builder maps the few first-class fields ``RecordContext`` already models
(equipment_id, area, site, batch/lot/recipe, operating_mode, shift, operator)
and passes **every remaining field** through into ``RecordContext.extra``.
Pass-through is intentional: governance records produced by the supervisor
and the plant-wide coordinator carry rich, event-specific payloads that the
hub must see verbatim, and the source of these dicts is in-tree code (not
user input), so allowlisting per field would just create silent-loss bugs.
"""

from __future__ import annotations

from typing import Any

from forge.core.models.contextual_record import RecordContext

# First-class fields modeled on RecordContext itself — copied to the typed
# attributes and excluded from ``extra``.
_FIRST_CLASS_FIELDS = frozenset(
    {
        "equipment_id",
        "area",
        "site",
        "batch_id",
        "lot_id",
        "recipe_id",
        "operating_mode",
        "shift",
        "operator_id",
    }
)

# Fields ``record_builder`` consumes for the value / timestamp / quality
# slots of the ContextualRecord — not part of the operational context.
_VALUE_FIELDS = frozenset(
    {"value", "timestamp", "engineering_units", "quality", "error"}
)


def build_record_context(raw_event: dict[str, Any]) -> RecordContext:
    """Transform a raw control event into a ``RecordContext``.

    Args:
        raw_event: A control decision / diagnostic / optimization-result dict
            produced by the controller, model-identification, supervisor, or
            optimization layers.

    Returns:
        A ``RecordContext`` with OT control metadata attached. Fields that
        aren't first-class on :class:`RecordContext` and aren't consumed by
        :mod:`plc_workflows_mpc.record_builder` flow through into ``extra``.
    """
    extra: dict[str, Any] = {
        key: value
        for key, value in raw_event.items()
        if key not in _FIRST_CLASS_FIELDS
        and key not in _VALUE_FIELDS
        and value is not None
    }
    return RecordContext(
        equipment_id=raw_event.get("equipment_id"),
        area=raw_event.get("area"),
        site=raw_event.get("site"),
        batch_id=raw_event.get("batch_id"),
        lot_id=raw_event.get("lot_id"),
        recipe_id=raw_event.get("recipe_id"),
        operating_mode=raw_event.get("operating_mode"),
        shift=raw_event.get("shift"),
        operator_id=raw_event.get("operator_id"),
        extra=extra,
    )
