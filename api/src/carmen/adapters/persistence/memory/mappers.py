"""Memoria de planes: tabla ⇄ dominio. El plan viaja en su forma canónica (canonical_json)."""

from sqlalchemy import RowMapping

from carmen.adapters.persistence.types import as_mapping, loads, vector_value
from carmen.application.ports.repositories import MemoryExample, MemoryExampleDraft, MemoryId
from carmen.domain.locale import Locale
from carmen.domain.plan.canonical import canonical_json, plan_from_dict
from carmen.domain.time import Instant


def example_row(memory_id: MemoryId, e: MemoryExampleDraft, now: Instant) -> dict[str, object]:
    return {
        "id": str(memory_id),
        "question_norm": e.question_norm,
        "question": e.question,
        "embedding": vector_value(e.embedding),
        "plan": canonical_json(e.plan),
        "plan_schema_version": e.plan.schema_version,
        "systems": sorted(str(s) for s in e.plan.systems),
        "locale": e.locale.value,
        "hits": 1,
        "validated_by": None if e.validated_by is None else str(e.validated_by),
        "active": True,
        "created_at": now.at,
        "updated_at": now.at,
    }


def example_from_row(r: RowMapping) -> MemoryExample:
    return MemoryExample(
        memory_id=MemoryId(r["id"]),
        question=r["question"],
        plan=plan_from_dict(as_mapping(loads(r["plan"]))),
        locale=Locale(r["locale"]),
        similarity=float(r["similarity"]),
        hits=int(r["hits"]),
    )
