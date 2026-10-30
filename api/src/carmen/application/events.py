"""Eventos del turno: lo que la aplicación emite y presentación traduce a SSE 1.1 (6.5).

Una carga tipada por tipo de evento, con los mismos campos que contracts/sse-events.schema.json.
La envoltura del cable (event_id, schema_version) la pone presentación; aquí basta con la
correlación, el orden y el instante.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import ClassVar

from carmen.domain.approval.models import Impact
from carmen.domain.conversation.turn import TurnStatus
from carmen.domain.delegation.models import AgentResultStatus
from carmen.domain.errors import ValidationError
from carmen.domain.ids import (
    AgentId,
    ApprovalId,
    CallId,
    ClaimId,
    ConversationId,
    CorrelationId,
    DelegationPlanId,
    MessageId,
    StepId,
    TaskId,
)
from carmen.domain.orchestration.mode import ResponseMode
from carmen.domain.system import SystemId
from carmen.domain.text import require_non_negative, require_text
from carmen.domain.time import Instant


class EventType(StrEnum):
    MODE = "mode"
    STAGE = "stage"
    DELEGATION = "delegation"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    AGENT_RESULT = "agent_result"
    APPROVAL_REQUIRED = "approval_required"
    DELTA = "delta"
    GROUNDING = "grounding"
    WARNING = "warning"
    ERROR = "error"
    DONE = "done"


class DeltaSection(StrEnum):
    DATA = "data"
    READING = "reading"


@dataclass(frozen=True, slots=True)
class ModePayload:
    event_type: ClassVar[EventType] = EventType.MODE

    response_mode: ResponseMode


@dataclass(frozen=True, slots=True)
class StagePayload:
    event_type: ClassVar[EventType] = EventType.STAGE

    stage: str
    detail: str | None = None
    step_id: StepId | None = None

    def __post_init__(self) -> None:
        require_text("stage", self.stage)


@dataclass(frozen=True, slots=True)
class DelegationPayload:
    """Se anuncia la tarea, nunca sus herramientas (6.5)."""

    event_type: ClassVar[EventType] = EventType.DELEGATION

    task_id: TaskId
    agent_id: AgentId
    depends_on: tuple[TaskId, ...]


@dataclass(frozen=True, slots=True)
class ToolCallPayload:
    event_type: ClassVar[EventType] = EventType.TOOL_CALL

    agent_id: AgentId
    task_id: TaskId
    step_id: StepId
    call_id: CallId
    system_id: SystemId
    tool_name: str
    arguments_digest: str


@dataclass(frozen=True, slots=True)
class ToolResultPayload:
    event_type: ClassVar[EventType] = EventType.TOOL_RESULT

    agent_id: AgentId
    task_id: TaskId
    step_id: StepId
    call_id: CallId
    ok: bool
    facts_count: int
    ms: int
    partial: bool

    def __post_init__(self) -> None:
        require_non_negative("facts_count", self.facts_count)
        require_non_negative("ms", self.ms)


@dataclass(frozen=True, slots=True)
class AgentResultPayload:
    event_type: ClassVar[EventType] = EventType.AGENT_RESULT

    task_id: TaskId
    agent_id: AgentId
    status: AgentResultStatus
    evidence_count: int
    ms: int

    def __post_init__(self) -> None:
        require_non_negative("evidence_count", self.evidence_count)
        require_non_negative("ms", self.ms)


@dataclass(frozen=True, slots=True)
class ApprovalRequiredPayload:
    event_type: ClassVar[EventType] = EventType.APPROVAL_REQUIRED

    request_id: ApprovalId
    agent_id: AgentId
    summary: str
    impact: Impact
    expires_at: Instant

    def __post_init__(self) -> None:
        require_text("summary", self.summary)


@dataclass(frozen=True, slots=True)
class DeltaPayload:
    event_type: ClassVar[EventType] = EventType.DELTA

    section: DeltaSection
    text: str


@dataclass(frozen=True, slots=True)
class UnsupportedClaim:
    claim_id: ClaimId
    raw_value: str


@dataclass(frozen=True, slots=True)
class GroundingPayload:
    event_type: ClassVar[EventType] = EventType.GROUNDING

    ok: bool
    checked: int
    unsupported: tuple[UnsupportedClaim, ...]

    def __post_init__(self) -> None:
        require_non_negative("checked", self.checked)


@dataclass(frozen=True, slots=True)
class WarningPayload:
    event_type: ClassVar[EventType] = EventType.WARNING

    code: str
    message: str
    system_id: SystemId | None = None
    agent_id: AgentId | None = None

    def __post_init__(self) -> None:
        require_text("code", self.code)
        require_text("message", self.message)


@dataclass(frozen=True, slots=True)
class ErrorPayload:
    event_type: ClassVar[EventType] = EventType.ERROR

    code: str
    message: str
    recoverable: bool

    def __post_init__(self) -> None:
        require_text("code", self.code)
        require_text("message", self.message)


@dataclass(frozen=True, slots=True)
class DonePayload:
    event_type: ClassVar[EventType] = EventType.DONE

    message_id: MessageId
    conversation_id: ConversationId
    status: TurnStatus
    partial: bool
    missing_systems: tuple[SystemId, ...]
    grounding_ok: bool | None
    plan_id: DelegationPlanId | None
    round: int
    repairs: int
    latency_ms: int
    model: str
    catalog_versions: Mapping[SystemId, str]
    response_mode: ResponseMode
    agents_used: tuple[AgentId, ...]
    missing_agents: tuple[AgentId, ...]

    def __post_init__(self) -> None:
        require_non_negative("round", self.round)
        require_non_negative("repairs", self.repairs)
        require_non_negative("latency_ms", self.latency_ms)
        require_text("model", self.model)
        if self.response_mode.delegates is (self.plan_id is None):
            msg = "done lleva plan_id si y solo si el turno delegó"
            raise ValidationError(msg)
        object.__setattr__(self, "catalog_versions", MappingProxyType(dict(self.catalog_versions)))


EventPayload = (
    ModePayload
    | StagePayload
    | DelegationPayload
    | ToolCallPayload
    | ToolResultPayload
    | AgentResultPayload
    | ApprovalRequiredPayload
    | DeltaPayload
    | GroundingPayload
    | WarningPayload
    | ErrorPayload
    | DonePayload
)


@dataclass(frozen=True, slots=True)
class DomainEvent:
    """Un evento del turno. sequence empieza en 1 y crece sin huecos dentro de la correlación."""

    correlation_id: CorrelationId
    sequence: int
    occurred_at: Instant
    payload: EventPayload

    def __post_init__(self) -> None:
        if (
            isinstance(self.sequence, bool)
            or not isinstance(self.sequence, int)
            or self.sequence < 1
        ):
            msg = f"sequence debe ser un entero >= 1: {self.sequence!r}"
            raise ValidationError(msg)

    @property
    def event_type(self) -> EventType:
        return self.payload.event_type
