"""Aprobación humana: una barrera del protocolo, no una instrucción del prompt (6.12.6)."""

from dataclasses import dataclass
from enum import StrEnum

from carmen.domain.errors import ValidationError
from carmen.domain.evidence.models import EvidenceReference
from carmen.domain.ids import AgentId, ApprovalId, PrincipalId, TurnId
from carmen.domain.role import Role
from carmen.domain.text import require_text
from carmen.domain.time import Instant


class Impact(StrEnum):
    HIGH = "high"
    CRITICAL = "critical"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


@dataclass(frozen=True, slots=True)
class HumanApprovalRequest:
    request_id: ApprovalId
    turn_id: TurnId
    agent_id: AgentId
    action: str
    impact: Impact
    summary: str
    evidence_refs: tuple[EvidenceReference, ...]
    required_role: Role
    expires_at: Instant

    def __post_init__(self) -> None:
        require_text("action", self.action)
        require_text("summary", self.summary)


@dataclass(frozen=True, slots=True)
class ApprovalRecord:
    """Quién decidió, cuándo y sobre qué evidencia (ck_decided)."""

    request_id: ApprovalId
    status: ApprovalStatus
    evidence_refs: tuple[EvidenceReference, ...] = ()
    decided_by: PrincipalId | None = None
    decided_at: Instant | None = None

    def __post_init__(self) -> None:
        decided = self.status in (ApprovalStatus.APPROVED, ApprovalStatus.REJECTED)
        has_decider = self.decided_by is not None and self.decided_at is not None
        if decided and not has_decider:
            msg = f"{self.request_id}: {self.status} exige decided_by y decided_at"
            raise ValidationError(msg)
        if self.status is ApprovalStatus.PENDING and (
            self.decided_by is not None or self.decided_at is not None
        ):
            msg = f"{self.request_id}: una petición pendiente no tiene decisor"
            raise ValidationError(msg)

    @property
    def approved(self) -> bool:
        return self.status is ApprovalStatus.APPROVED
