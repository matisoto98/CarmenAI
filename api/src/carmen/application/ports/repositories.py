"""Repositorios del supervisor (5.5, 7.3, 7.4, 7.8.4, 7.9.7).

Cada método que el documento declara atómico o idempotente lo dice en su docstring, y los
dobles en memoria lo cumplen: así las pruebas de aplicación ya dependen de esas garantías.
"""

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from enum import IntEnum, StrEnum
from typing import Protocol

from carmen.application.context import Requester
from carmen.application.jsontypes import JsonObject
from carmen.application.ports.embeddings import Vector
from carmen.domain.agents.card import AgentLifecycleState
from carmen.domain.approval.models import ApprovalRecord, ApprovalStatus, HumanApprovalRequest
from carmen.domain.conversation.turn import ConversationTurn, TurnStatus
from carmen.domain.delegation.models import AgentResult
from carmen.domain.errors import ValidationError
from carmen.domain.evidence.models import EvidenceFact
from carmen.domain.ids import (
    AgentId,
    ApprovalId,
    CallId,
    ConversationId,
    CorrelationId,
    MessageId,
    PatternId,
    PrincipalId,
    StepId,
    TurnId,
)
from carmen.domain.locale import Locale
from carmen.domain.plan.models import QueryPlan
from carmen.domain.system import SystemId
from carmen.domain.text import require_non_negative, require_text
from carmen.domain.time import Instant

# --- Conversaciones y mensajes (7.3, unidad de trabajo 1 de 7.4) ---


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True, slots=True)
class NewConversation:
    conversation_id: ConversationId
    owner: PrincipalId
    locale: Locale
    created_at: Instant
    channel: str = "web"
    title: str | None = None

    def __post_init__(self) -> None:
        require_text("channel", self.channel)


@dataclass(frozen=True, slots=True)
class NewMessage:
    message_id: MessageId
    conversation_id: ConversationId
    role: MessageRole
    content: str
    status: TurnStatus
    correlation_id: CorrelationId
    created_at: Instant
    locale: Locale | None = None


@dataclass(frozen=True, slots=True)
class NewToolCall:
    call_id: CallId
    message_id: MessageId
    step_id: StepId
    system_id: SystemId
    tool_name: str
    arguments: JsonObject
    ok: bool
    created_at: Instant
    error_code: str | None = None
    facts_count: int = 0
    partial: bool = False
    repaired: bool = False
    ms: int | None = None

    def __post_init__(self) -> None:
        require_text("tool_name", self.tool_name)
        require_non_negative("facts_count", self.facts_count)
        if self.ok is (self.error_code is not None):
            msg = "una llamada fallida lleva error_code; una correcta, no"
            raise ValidationError(msg)


@dataclass(frozen=True, slots=True)
class ThreadMessage:
    message_id: MessageId
    role: MessageRole
    content: str
    status: TurnStatus
    created_at: Instant


@dataclass(frozen=True, slots=True)
class ConversationThread:
    conversation_id: ConversationId
    owner: PrincipalId
    locale: Locale
    messages: tuple[ThreadMessage, ...]
    title: str | None = None


class Rating(IntEnum):
    DOWN = -1
    UP = 1


@dataclass(frozen=True, slots=True)
class Feedback:
    message_id: MessageId
    principal_id: PrincipalId
    rating: Rating
    at: Instant
    comment: str | None = None


class FeedbackOutcome(StrEnum):
    CREATED = "created"
    UPDATED = "updated"
    UNCHANGED = "unchanged"


class ConversationRepository(Protocol):
    async def create(self, c: NewConversation) -> ConversationId: ...

    async def append_message(self, m: NewMessage, calls: Sequence[NewToolCall]) -> MessageId:
        """UNA transacción: mensaje y llamadas se persisten juntos o no se persiste ninguno."""
        ...

    async def touch(self, cid: ConversationId, at: Instant) -> None: ...

    async def get_thread(
        self, cid: ConversationId, requester: Requester
    ) -> ConversationThread | None:
        """None tanto si no existe como si es de otra persona: no se revela cuál de las dos."""
        ...

    async def record_feedback(self, f: Feedback) -> FeedbackOutcome:
        """IDEMPOTENTE por (message_id, principal_id)."""
        ...


class TurnRepository(Protocol):
    async def save(
        self,
        turn: ConversationTurn,
        *,
        message_id: MessageId,
        results: Sequence[AgentResult] = (),
    ) -> None:
        """En la misma unidad de trabajo que el mensaje del asistente, que ES el turno (7.3.1).

        `message_id` es ese mensaje, ya guardado con sus llamadas. `results` son los AgentResult
        cuyas ejecuciones lleva el turno, en el mismo orden que `turn.runs`: aportan la tarea, la
        versión del agente y el estado de cada ejecución. Un turno ya guardado no se reescribe:
        lanza ValidationError, igual que un resultado que no corresponde a una ejecución.
        """
        ...

    async def get(self, turn_id: TurnId) -> ConversationTurn | None: ...


# --- Memoria de planes, lagunas, corpus y brief (7.3, unidades 2, 3 y 5 de 7.4) ---


class MemoryId(PatternId):
    __slots__ = ()
    pattern = re.compile(r"^mem_[a-z0-9]{4,32}$")


@dataclass(frozen=True, slots=True)
class MemoryExampleDraft:
    question_norm: str
    question: str
    embedding: Vector
    plan: QueryPlan
    locale: Locale
    validated_by: PrincipalId | None = None

    def __post_init__(self) -> None:
        require_text("question_norm", self.question_norm)
        require_text("question", self.question)


@dataclass(frozen=True, slots=True)
class MemoryExample:
    memory_id: MemoryId
    question: str
    plan: QueryPlan
    locale: Locale
    similarity: float
    hits: int


class MemoryRepository(Protocol):
    async def similar_plans(self, v: Vector, k: int, min_sim: float) -> list[MemoryExample]:
        """Solo ejemplos activos con similitud >= min_sim, de más a menos parecido."""
        ...

    async def upsert_example(self, e: MemoryExampleDraft) -> MemoryId:
        """Incremento de aciertos ATÓMICO por (question_norm, locale)."""
        ...

    async def deactivate(self, mid: MemoryId, by: PrincipalId) -> None: ...


class GapId(PatternId):
    __slots__ = ()
    pattern = re.compile(r"^gap_[a-z0-9]{4,32}$")


class GapStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


@dataclass(frozen=True, slots=True)
class GapDraft:
    question_norm: str
    question: str
    embedding: Vector
    locale: Locale
    reason: str
    at: Instant

    def __post_init__(self) -> None:
        require_text("question_norm", self.question_norm)
        require_text("question", self.question)
        require_text("reason", self.reason)


@dataclass(frozen=True, slots=True)
class GapFilter:
    status: GapStatus | None = GapStatus.OPEN
    locale: Locale | None = None
    min_occurrences: int = 1
    limit: int = 50

    def __post_init__(self) -> None:
        if self.min_occurrences < 1 or self.limit < 1:
            msg = "min_occurrences y limit deben ser >= 1"
            raise ValidationError(msg)


@dataclass(frozen=True, slots=True)
class GapCluster:
    """Lagunas agrupadas. Sin agrupar todavía, cada laguna es su propio grupo sin nombre."""

    cluster_name: str | None
    locale: Locale
    questions: tuple[str, ...]
    occurrences: int
    last_seen: Instant


class GapRepository(Protocol):
    async def record(self, g: GapDraft) -> GapId:
        """Atómico: crea o incrementa occurrences sin condición de carrera."""
        ...

    async def list_clusters(self, f: GapFilter) -> list[GapCluster]:
        """De más a menos ocurrencias."""
        ...


@dataclass(frozen=True, slots=True)
class KnowledgeChunk:
    source: str
    chunk_ix: int
    title: str
    content: str
    similarity: float


class KnowledgeRepository(Protocol):
    async def search(self, v: Vector, k: int, min_sim: float) -> list[KnowledgeChunk]:
        """Por debajo del umbral devuelve lista VACÍA. Nunca el más parecido: así es como se
        inventa un nombre plausible.
        """
        ...


@dataclass(frozen=True, slots=True)
class SituationBrief:
    """Lo último que se supo de la red, con su antigüedad: un brief viejo se sirve avisando."""

    generated_at: Instant
    facts: tuple[EvidenceFact, ...]

    def age_seconds(self, now: Instant) -> int:
        return max(0, int((now.at - self.generated_at.at).total_seconds()))


class BriefRepository(Protocol):
    async def get(self) -> SituationBrief | None: ...

    async def put(self, b: SituationBrief) -> None:
        """Fila única: sustituye al brief anterior (unidad de trabajo 5)."""
        ...


# --- Glosario y temas (7.8.4) ---


def normalize_term(text: str) -> str:
    """Clave del glosario: minúsculas, sin tildes y con espacios simples."""
    decomposed = unicodedata.normalize("NFKD", text)
    plain = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(plain.lower().split())


class TermSource(StrEnum):
    SEED = "seed"
    ADMIN = "admin"


@dataclass(frozen=True, slots=True)
class GlossaryTerm:
    term: str
    display: str
    definition: str
    aliases: tuple[str, ...] = ()
    canonical: bool = False
    active: bool = True
    source: TermSource = TermSource.SEED

    def __post_init__(self) -> None:
        require_text("display", self.display)
        require_text("definition", self.definition)
        if self.term != normalize_term(self.term) or not self.term:
            msg = f"la clave del glosario debe estar normalizada: {self.term!r}"
            raise ValidationError(msg)


class GlossaryAction(StrEnum):
    CREATE = "create"
    UPDATE = "update"
    DEACTIVATE = "deactivate"


@dataclass(frozen=True, slots=True)
class GlossaryChange:
    term: str
    action: GlossaryAction
    actor: PrincipalId
    at: Instant
    before: GlossaryTerm | None = None
    after: GlossaryTerm | None = None


class GlossaryRepository(Protocol):
    async def list_active(self) -> tuple[GlossaryTerm, ...]:
        """Ordenados por clave."""
        ...

    async def get(self, term: str) -> GlossaryTerm | None: ...

    async def upsert(self, t: GlossaryTerm, actor: PrincipalId, at: Instant) -> GlossaryChange:
        """Cambio e historial en la misma transacción."""
        ...

    async def deactivate(self, term: str, actor: PrincipalId, at: Instant) -> GlossaryChange:
        """Lanza ValidationError si el término no existe o ya está inactivo."""
        ...

    async def history(self, term: str) -> tuple[GlossaryChange, ...]: ...


class TopicId(PatternId):
    __slots__ = ()
    pattern = re.compile(r"^top_[a-z0-9]{4,32}$")


class TopicStatus(StrEnum):
    OBSERVANDO = "observando"
    PLANIFICADO = "planificado"
    FUERA_ALCANCE = "fuera_alcance"
    CUBIERTO = "cubierto"


@dataclass(frozen=True, slots=True)
class Topic:
    topic_id: TopicId
    label: str
    asked: int
    resolved: int
    unresolved: int
    systems: frozenset[SystemId]
    status: TopicStatus
    first_seen: Instant
    last_seen: Instant

    def __post_init__(self) -> None:
        require_text("label", self.label)
        for name in ("asked", "resolved", "unresolved"):
            require_non_negative(name, getattr(self, name))
        if self.resolved + self.unresolved > self.asked:
            msg = "resueltas más no resueltas no pueden superar las preguntadas"
            raise ValidationError(msg)


class TopicRepository(Protocol):
    async def upsert(self, t: Topic) -> None: ...

    async def list_by_demand(self, limit: int) -> list[Topic]:
        """De más a menos preguntado (ix_topics_demand)."""
        ...

    async def set_status(self, tid: TopicId, status: TopicStatus, at: Instant) -> Topic:
        """Lanza ValidationError si el tema no existe."""
        ...


# --- Aprobación humana y ciclo de vida de agentes (7.3.1) ---


class ApprovalRepository(Protocol):
    async def create(self, request: HumanApprovalRequest) -> ApprovalRecord:
        """Nace pendiente."""
        ...

    async def get(self, request_id: ApprovalId) -> ApprovalRecord | None: ...

    async def decide(
        self, request_id: ApprovalId, status: ApprovalStatus, by: PrincipalId, at: Instant
    ) -> ApprovalRecord:
        """Solo desde pending y antes de expires_at; si no, lanza InvalidTransitionError."""
        ...

    async def expire_due(self, now: Instant) -> tuple[ApprovalId, ...]:
        """Caduca, en una sola operación, las pendientes cuyo plazo venció."""
        ...


@dataclass(frozen=True, slots=True)
class AgentLifecycleEntry:
    agent_id: AgentId
    state: AgentLifecycleState
    version: str
    updated_at: Instant
    owner: str | None = None
    certified_at: Instant | None = None
    report_ref: str | None = None

    def __post_init__(self) -> None:
        require_text("version", self.version)
        certified = self.owner and self.certified_at is not None and self.report_ref
        if self.state is AgentLifecycleState.CERTIFIED and not certified:
            msg = f"{self.agent_id}: CERTIFIED exige owner, certified_at y report_ref"
            raise ValidationError(msg)


@dataclass(frozen=True, slots=True)
class LifecycleChange:
    agent_id: AgentId
    from_state: AgentLifecycleState | None
    to_state: AgentLifecycleState
    reason: str
    actor: PrincipalId
    at: Instant

    def __post_init__(self) -> None:
        require_text("reason", self.reason)


class AgentLifecycleRepository(Protocol):
    async def register(self, entry: AgentLifecycleEntry, actor: PrincipalId) -> None:
        """Alta en DISCOVERED, con su primera fila de historial. Lanza ValidationError si existe."""
        ...

    async def get(self, agent_id: AgentId) -> AgentLifecycleEntry | None: ...

    async def transition(
        self, entry: AgentLifecycleEntry, reason: str, actor: PrincipalId
    ) -> LifecycleChange:
        """Estado nuevo e historial en la misma transacción. Solo las transiciones de 7.11.2:
        si no, lanza InvalidTransitionError.
        """
        ...

    async def history(self, agent_id: AgentId) -> tuple[LifecycleChange, ...]:
        """Del más reciente al más antiguo (ix_alh_agent)."""
        ...
