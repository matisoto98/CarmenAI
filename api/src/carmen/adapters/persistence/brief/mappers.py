"""Brief: tabla ⇄ dominio. Cada valor de hecho guarda su tipo; un Decimal viaja como texto
para que ni su precisión ni su escala cambien por el camino.
"""

from collections.abc import Mapping
from decimal import Decimal

from carmen.adapters.persistence.types import as_mapping, as_sequence, dumps, loads
from carmen.application.jsontypes import JsonValue
from carmen.application.ports.repositories import SituationBrief
from carmen.domain.errors import ValidationError
from carmen.domain.evidence.models import (
    EntityRef,
    EvidenceFact,
    FactValue,
    PeriodInterpreted,
    Provenance,
    Unit,
)
from carmen.domain.ids import CallId, FactId
from carmen.domain.system import SystemId
from carmen.domain.time import Instant

PAYLOAD_VERSION = 1


def _value_to_json(value: FactValue) -> JsonValue:
    if value is None:
        return {"type": "null"}
    if isinstance(value, bool):
        return {"type": "bool", "value": value}
    if isinstance(value, int):
        return {"type": "int", "value": value}
    if isinstance(value, Decimal):
        return {"type": "decimal", "value": str(value)}
    return {"type": "str", "value": value}


def _value_from_json(data: Mapping[str, JsonValue]) -> FactValue:
    kind, raw = data.get("type"), data.get("value")
    if kind == "null":
        return None
    if kind == "bool" and isinstance(raw, bool):
        return raw
    if kind == "int" and isinstance(raw, int) and not isinstance(raw, bool):
        return raw
    if kind == "decimal" and isinstance(raw, str):
        return Decimal(raw)
    if kind == "str" and isinstance(raw, str):
        return raw
    msg = f"valor de hecho mal codificado en el brief: {dict(data)!r}"
    raise ValidationError(msg)


def _optional_text(data: Mapping[str, JsonValue], key: str) -> str | None:
    value = data.get(key)
    if value is None or isinstance(value, str):
        return value
    msg = f"{key} debe ser texto o null"
    raise ValidationError(msg)


def _text(data: Mapping[str, JsonValue], key: str) -> str:
    value = _optional_text(data, key)
    if value is None:
        msg = f"falta {key} en el brief"
        raise ValidationError(msg)
    return value


def fact_to_json(f: EvidenceFact) -> JsonValue:
    return {
        "fact_id": str(f.fact_id),
        "call_id": str(f.call_id),
        "system_id": str(f.system_id),
        "label": f.label,
        "value": _value_to_json(f.value),
        "provenance": {
            "tool_name": f.provenance.tool_name,
            "catalog_version": f.provenance.catalog_version,
            "generated_at": f.provenance.generated_at.isoformat(),
        },
        "metric": f.metric,
        "unit": None if f.unit is None else f.unit.value,
        "entity": None
        if f.entity is None
        else {"type": f.entity.type, "id": f.entity.id, "name": f.entity.name},
        "dimensions": dict(f.dimensions),
        "period": None
        if f.period is None
        else {
            "expression": f.period.expression,
            "start": f.period.start.isoformat(),
            "end": f.period.end.isoformat(),
            "text": f.period.text,
        },
    }


def fact_from_json(value: JsonValue) -> EvidenceFact:
    data = as_mapping(value)
    provenance = as_mapping(data.get("provenance"))
    entity = data.get("entity")
    period = data.get("period")
    unit = _optional_text(data, "unit")
    dimensions = as_mapping(data.get("dimensions", {}))
    return EvidenceFact(
        fact_id=FactId(_text(data, "fact_id")),
        call_id=CallId(_text(data, "call_id")),
        system_id=SystemId(_text(data, "system_id")),
        label=_text(data, "label"),
        value=_value_from_json(as_mapping(data.get("value"))),
        provenance=Provenance(
            tool_name=_text(provenance, "tool_name"),
            catalog_version=_text(provenance, "catalog_version"),
            generated_at=Instant.parse(_text(provenance, "generated_at")),
        ),
        metric=_optional_text(data, "metric"),
        unit=None if unit is None else Unit(unit),
        entity=None
        if entity is None
        else EntityRef(
            _text(as_mapping(entity), "type"),
            _text(as_mapping(entity), "id"),
            _optional_text(as_mapping(entity), "name"),
        ),
        dimensions={k: _text(dimensions, k) for k in dimensions},
        period=None
        if period is None
        else PeriodInterpreted(
            expression=_text(as_mapping(period), "expression"),
            start=Instant.parse(_text(as_mapping(period), "start")),
            end=Instant.parse(_text(as_mapping(period), "end")),
            text=_text(as_mapping(period), "text"),
        ),
    )


def brief_payload(b: SituationBrief) -> str:
    return dumps({"version": PAYLOAD_VERSION, "facts": [fact_to_json(f) for f in b.facts]})


def brief_from_row(payload: str, generated_at: Instant) -> SituationBrief:
    data = as_mapping(loads(payload))
    if data.get("version") != PAYLOAD_VERSION:
        msg = f"versión de brief desconocida: {data.get('version')!r}"
        raise ValidationError(msg)
    return SituationBrief(
        generated_at=generated_at,
        facts=tuple(fact_from_json(f) for f in as_sequence(data.get("facts"))),
    )
