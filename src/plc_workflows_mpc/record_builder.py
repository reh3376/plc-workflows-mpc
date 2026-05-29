"""Record builder — assemble ``ContextualRecord`` objects from control events.

Takes a raw control event plus its ``RecordContext`` and produces a complete
``ContextualRecord`` (source attribution, timestamps, value, lineage) ready for
hub ingestion. Every controller move and optimization decision becomes a
governed, auditable record.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from forge.core.models.contextual_record import (
    ContextualRecord,
    QualityCode,
    RecordContext,
    RecordLineage,
    RecordSource,
    RecordTimestamp,
    RecordValue,
)

_SOURCE_SYSTEM = "plc-workflows-mpc"
_SCHEMA_REF = "forge://schemas/plc-workflows-mpc/v0.1.0"


def build_contextual_record(
    *,
    raw_event: dict[str, Any],
    context: RecordContext,
    adapter_id: str,
    adapter_version: str,
) -> ContextualRecord:
    """Assemble a ``ContextualRecord`` from a raw control event.

    Args:
        raw_event: The control decision / diagnostic dict.
        context: Pre-built context from ``context.build_record_context()``.
        adapter_id: Adapter manifest ID.
        adapter_version: Adapter manifest version.

    Returns:
        A fully populated ``ContextualRecord``.
    """
    source_time = _parse_timestamp(raw_event.get("timestamp"))
    raw_value = raw_event.get("value")

    return ContextualRecord(
        source=RecordSource(
            adapter_id=adapter_id,
            system=_SOURCE_SYSTEM,
            tag_path=_derive_tag_path(raw_event),
        ),
        timestamp=RecordTimestamp(
            source_time=source_time,
            ingestion_time=datetime.now(tz=UTC),
        ),
        value=RecordValue(
            raw=raw_value,
            engineering_units=raw_event.get("engineering_units"),
            quality=_assess_quality(raw_event),
            data_type=_infer_data_type(raw_value),
        ),
        context=context,
        lineage=RecordLineage(
            schema_ref=_SCHEMA_REF,
            adapter_id=adapter_id,
            adapter_version=adapter_version,
        ),
    )


def _parse_timestamp(value: Any) -> datetime:
    """Parse an ISO-8601 string or datetime into a tz-aware datetime."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return datetime.now(tz=UTC)


def _derive_tag_path(raw_event: dict[str, Any]) -> str:
    """Derive the source tag path for a control event."""
    mv_tag = raw_event.get("mv_tag")
    if isinstance(mv_tag, str) and mv_tag:
        return mv_tag
    loop_id = raw_event.get("loop_id", "unknown")
    event_type = raw_event.get("event_type", "event")
    return f"{loop_id}.{event_type}"


def _infer_data_type(value: Any) -> str:
    """Infer a coarse data type label from a Python value."""
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int64"
    if isinstance(value, float):
        return "float64"
    if isinstance(value, str):
        return "string"
    return "object"


def _assess_quality(raw_event: dict[str, Any]) -> QualityCode:
    """Map a raw quality hint to a ``QualityCode``, defaulting to GOOD."""
    if raw_event.get("error"):
        return QualityCode.BAD
    raw_quality = raw_event.get("quality")
    if isinstance(raw_quality, str):
        try:
            return QualityCode(raw_quality.upper())
        except ValueError:
            return QualityCode.UNCERTAIN
    return QualityCode.GOOD
