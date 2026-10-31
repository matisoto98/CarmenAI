"""Evidencia y anclaje del turno: hechos, pasajes, adjuntos y afirmaciones (6.3, 6.9.2).

Cada elemento cuelga de la llamada que lo devolvió (tool_call_id) y guarda su posición en el
turno (ord), común a los tres tipos, para que la evidencia se reconstruya en el mismo orden.
Un hecho guarda su valor exacto: un número en value_num y un texto o un booleano en value_text,
con value_kind para devolverlo con su tipo.
"""

from collections.abc import Mapping
from decimal import Decimal
from uuid import UUID

from sqlalchemy import RowMapping

from carmen.adapters.persistence.types import as_mapping, dumps, instant, loads
from carmen.domain.errors import ValidationError
from carmen.domain.evidence.grounding import GroundingClaim, TextSpan, Verdict
from carmen.domain.evidence.models import (
    EntityRef,
    EvidenceFact,
    EvidenceMedia,
    EvidencePassage,
    EvidenceReference,
    FactValue,
    PeriodInterpreted,
    Provenance,
    Unit,
)
from carmen.domain.ids import CallId, ClaimId, FactId, MediaId, MessageId, PassageId
from carmen.domain.system import SystemId
from carmen.domain.time import Instant

type Values = dict[str, object]


def _split_value(value: FactValue) -> tuple[str, Decimal | None, str | None]:
    if value is None:
        return "null", None, None
    if isinstance(value, bool):
        return "bool", None, "true" if value else "false"
    if isinstance(value, int):
        return "int", Decimal(value), None
    if isinstance(value, Decimal):
        return "decimal", value, None
    return "str", None, value


def _join_value(kind: str, number: Decimal | None, text: str | None) -> FactValue:
    if kind == "null":
        return None
    if kind == "bool" and text in ("true", "false"):
        return text == "true"
    if kind == "int" and number is not None:
        return int(number)
    if kind == "decimal" and number is not None:
        return number
    if kind == "str" and text is not None:
        return text
    msg = f"valor de hecho incoherente en la base: {kind}, {number!r}, {text!r}"
    raise ValidationError(msg)


def _period_json(p: PeriodInterpreted | None) -> str | None:
    if p is None:
        return None
    return dumps(
        {
            "expression": p.expression,
            "start": p.start.isoformat(),
            "end": p.end.isoformat(),
            "text": p.text,
        }
    )


def _period(text: str | None) -> PeriodInterpreted | None:
    if text is None:
        return None
    data = as_mapping(loads(text))
    return PeriodInterpreted(
        expression=str(data["expression"]),
        start=Instant.parse(str(data["start"])),
        end=Instant.parse(str(data["end"])),
        text=str(data["text"]),
    )


def _dimensions(text: str) -> Mapping[str, str]:
    return {k: str(v) for k, v in as_mapping(loads(text)).items()}


def fact_row(message_id: MessageId, tool_call_id: UUID, ord_: int, f: EvidenceFact) -> Values:
    kind, value_num, value_text = _split_value(f.value)
    return {
        "message_id": str(message_id),
        "tool_call_id": tool_call_id,
        "ord": ord_,
        "fact_key": str(f.fact_id),
        "label": f.label,
        "value_kind": kind,
        "value_num": value_num,
        "value_text": value_text,
        "unit": None if f.unit is None else f.unit.value,
        "entity_type": None if f.entity is None else f.entity.type,
        "entity_id": None if f.entity is None else f.entity.id,
        "entity_name": None if f.entity is None else f.entity.name,
        "dimensions": dumps(dict(f.dimensions)),
        "period": _period_json(f.period),
        "system_id": str(f.system_id),
        "metric": f.metric,
        "provenance_tool": f.provenance.tool_name,
        "provenance_catalog_version": f.provenance.catalog_version,
        "provenance_generated_at": f.provenance.generated_at.at,
    }


def fact_from_row(r: RowMapping) -> EvidenceFact:
    entity = (
        None
        if r["entity_type"] is None
        else EntityRef(r["entity_type"], r["entity_id"], r["entity_name"])
    )
    return EvidenceFact(
        fact_id=FactId(r["fact_key"]),
        call_id=CallId(r["call_id"]),
        system_id=SystemId(r["system_id"]),
        label=r["label"],
        value=_join_value(r["value_kind"], r["value_num"], r["value_text"]),
        provenance=Provenance(
            r["provenance_tool"],
            r["provenance_catalog_version"],
            instant(r["provenance_generated_at"]),
        ),
        metric=r["metric"],
        unit=None if r["unit"] is None else Unit(r["unit"]),
        entity=entity,
        dimensions=_dimensions(r["dimensions"]),
        period=_period(r["period"]),
    )


def passage_row(message_id: MessageId, tool_call_id: UUID, ord_: int, p: EvidencePassage) -> Values:
    return {
        "message_id": str(message_id),
        "tool_call_id": tool_call_id,
        "ord": ord_,
        "passage_key": str(p.passage_id),
        "system_id": str(p.system_id),
        "document_id": p.document_id,
        "title": p.title,
        "body": p.text,
        "kind": p.kind,
        "relevance": p.relevance,
        "section": p.section,
        "anchor": p.anchor,
        "doc_version": p.doc_version,
        "updated_at": None if p.updated_at is None else p.updated_at.at,
        "url": p.url,
    }


def passage_from_row(r: RowMapping) -> EvidencePassage:
    return EvidencePassage(
        passage_id=PassageId(r["passage_key"]),
        call_id=CallId(r["call_id"]),
        system_id=SystemId(r["system_id"]),
        document_id=r["document_id"],
        title=r["title"],
        text=r["body"],
        kind=r["kind"],
        relevance=float(r["relevance"]),
        section=r["section"],
        anchor=r["anchor"],
        doc_version=r["doc_version"],
        updated_at=None if r["updated_at"] is None else instant(r["updated_at"]),
        url=r["url"],
    )


def media_row(message_id: MessageId, tool_call_id: UUID, ord_: int, m: EvidenceMedia) -> Values:
    return {
        "message_id": str(message_id),
        "tool_call_id": tool_call_id,
        "ord": ord_,
        "media_key": str(m.media_id),
        "system_id": str(m.system_id),
        "document_id": m.document_id,
        "mime": m.mime,
        "caption": m.caption,
        "uri": m.uri,
        "bytes": m.bytes,
        "anchor": m.anchor,
    }


def media_from_row(r: RowMapping) -> EvidenceMedia:
    return EvidenceMedia(
        media_id=MediaId(r["media_key"]),
        call_id=CallId(r["call_id"]),
        system_id=SystemId(r["system_id"]),
        document_id=r["document_id"],
        mime=r["mime"],
        caption=r["caption"],
        uri=r["uri"],
        bytes=None if r["bytes"] is None else int(r["bytes"]),
        anchor=r["anchor"],
    )


def claim_row(
    message_id: MessageId, ord_: int, c: GroundingClaim, fact_row_id: UUID | None
) -> Values:
    return {
        "message_id": str(message_id),
        "ord": ord_,
        "claim_key": str(c.claim_id),
        "span_start": c.text_span.start,
        "span_end": c.text_span.end,
        "raw_value": c.raw_value,
        "normalized": c.normalized,
        "verdict": c.verdict,
        "fact_id": fact_row_id,
        "reason": c.reason,
    }


def _verdict(text: str) -> Verdict:
    if text == "supported":
        return "supported"
    if text == "unsupported":
        return "unsupported"
    if text == "whitelisted":
        return "whitelisted"
    msg = f"veredicto desconocido en la base: {text!r}"
    raise ValidationError(msg)


def claim_from_row(r: RowMapping) -> GroundingClaim:
    support = (
        None
        if r["support_call_id"] is None
        else EvidenceReference(CallId(r["support_call_id"]), FactId(r["support_fact_key"]))
    )
    return GroundingClaim(
        claim_id=ClaimId(r["claim_key"]),
        text_span=TextSpan(int(r["span_start"]), int(r["span_end"])),
        raw_value=r["raw_value"],
        normalized=r["normalized"],
        supported_by=support,
        verdict=_verdict(r["verdict"]),
        reason=r["reason"],
    )
