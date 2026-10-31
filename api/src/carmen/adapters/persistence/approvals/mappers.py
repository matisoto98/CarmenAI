"""Aprobaciones: tabla ⇄ dominio."""

from sqlalchemy import RowMapping

from carmen.adapters.persistence.types import as_mapping, as_sequence, dumps, instant, loads
from carmen.domain.approval.models import ApprovalRecord, ApprovalStatus, HumanApprovalRequest
from carmen.domain.evidence.models import EvidenceReference
from carmen.domain.ids import ApprovalId, CallId, FactId, PrincipalId
from carmen.domain.time import Instant


def refs_to_json(refs: tuple[EvidenceReference, ...]) -> str:
    return dumps([{"call_id": str(r.call_id), "fact_id": str(r.fact_id)} for r in refs])


def refs_from_json(text: str) -> tuple[EvidenceReference, ...]:
    refs = []
    for item in as_sequence(loads(text)):
        data = as_mapping(item)
        refs.append(EvidenceReference(CallId(str(data["call_id"])), FactId(str(data["fact_id"]))))
    return tuple(refs)


def request_row(r: HumanApprovalRequest, now: Instant) -> dict[str, object]:
    return {
        "id": str(r.request_id),
        "turn_id": str(r.turn_id),
        "agent_id": str(r.agent_id),
        "action": r.action,
        "impact": r.impact.value,
        "summary": r.summary,
        "evidence_refs": refs_to_json(r.evidence_refs),
        "required_role": r.required_role.value,
        "status": ApprovalStatus.PENDING.value,
        "expires_at": r.expires_at.at,
        "created_at": now.at,
    }


def record_from_row(r: RowMapping) -> ApprovalRecord:
    return ApprovalRecord(
        request_id=ApprovalId(r["id"]),
        status=ApprovalStatus(r["status"]),
        evidence_refs=refs_from_json(r["evidence_refs"]),
        decided_by=None if r["decided_by"] is None else PrincipalId(r["decided_by"]),
        decided_at=None if r["decided_at"] is None else instant(r["decided_at"]),
    )
