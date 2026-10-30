"""ConversationTurn: un turno completo, la unidad de registro aunque no se delegue (6.12.8)."""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Final

from carmen.domain.approval.models import ApprovalRecord
from carmen.domain.delegation.models import AgentRun, DelegationPlan
from carmen.domain.errors import ValidationError
from carmen.domain.evidence.grounding import GroundingResult
from carmen.domain.evidence.models import EvidenceItem
from carmen.domain.ids import AgentId, ConversationId, PrincipalId, TurnId
from carmen.domain.orchestration.mode import ResponseMode
from carmen.domain.text import require_non_negative, require_text

MAX_REDELEGATIONS: Final = 1


class TurnStatus(StrEnum):
    """Estado final del turno, el mismo que el del mensaje (msg_status)."""

    COMPLETED = "completed"
    PARTIAL = "partial"
    REJECTED = "rejected"
    FAILED = "failed"
    CANCELLED = "cancelled"
    NO_DATA = "no_data"


@dataclass(frozen=True, slots=True)
class TokenUsage:
    tokens_in: int = 0
    tokens_out: int = 0

    def __post_init__(self) -> None:
        require_non_negative("tokens_in", self.tokens_in)
        require_non_negative("tokens_out", self.tokens_out)

    @property
    def total(self) -> int:
        return self.tokens_in + self.tokens_out


@dataclass(frozen=True, slots=True)
class ConversationTurn:
    turn_id: TurnId
    conversation_id: ConversationId
    principal_id: PrincipalId
    question: str
    response_mode: ResponseMode
    policy_version: str
    status: TurnStatus
    agents_used: tuple[AgentId, ...] = ()
    delegation_plan: DelegationPlan | None = None
    runs: tuple[AgentRun, ...] = ()
    evidence: tuple[EvidenceItem, ...] = ()
    grounding: GroundingResult | None = None
    approvals: tuple[ApprovalRecord, ...] = ()
    tokens: TokenUsage = TokenUsage()
    cost_eur: Decimal = Decimal(0)
    latency_ms: int = 0
    missing_agents: tuple[AgentId, ...] = ()
    redelegations: int = 0

    def __post_init__(self) -> None:
        require_text("question", self.question)
        require_text("policy_version", self.policy_version)
        require_non_negative("latency_ms", self.latency_ms)
        require_non_negative("redelegations", self.redelegations)
        if not self.cost_eur.is_finite() or self.cost_eur < 0:
            msg = "cost_eur debe ser >= 0"
            raise ValidationError(msg)
        if self.redelegations > MAX_REDELEGATIONS:
            msg = f"máximo {MAX_REDELEGATIONS} re-delegación por turno (6.12.5)"
            raise ValidationError(msg)
        if len(set(self.agents_used)) != len(self.agents_used):
            msg = "agents_used repite agentes"
            raise ValidationError(msg)
        if self.response_mode.delegates:
            self._check_delegated()
        else:
            self._check_not_delegated()

    def _check_not_delegated(self) -> None:
        """SUPERVISOR_DIRECT, CLARIFY y REFUSE no tocan ningún agente (ck_direct_sin_agentes)."""
        if self.agents_used or self.delegation_plan is not None or self.runs:
            msg = f"{self.response_mode} exige agents_used vacío, sin plan y sin ejecuciones"
            raise ValidationError(msg)
        if self.missing_agents or self.redelegations:
            msg = f"{self.response_mode} no puede tener agentes ausentes ni re-delegaciones"
            raise ValidationError(msg)

    def _check_delegated(self) -> None:
        plan = self.delegation_plan
        if plan is None:
            msg = f"{self.response_mode} exige un DelegationPlan"
            raise ValidationError(msg)
        if plan.response_mode is not self.response_mode or plan.turn_id != self.turn_id:
            msg = "el DelegationPlan es de otro turno o de otro modo"
            raise ValidationError(msg)
        ran = {run.agent_id for run in self.runs}
        if not ran <= set(self.agents_used):
            msg = "toda ejecución de agente aparece en agents_used"
            raise ValidationError(msg)
        if set(self.missing_agents) & ran:
            msg = "un agente no puede estar a la vez ausente y ejecutado"
            raise ValidationError(msg)
