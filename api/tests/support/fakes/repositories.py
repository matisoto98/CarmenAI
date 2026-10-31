"""Repositorios en memoria con las mismas garantías que declara cada puerto (7.4)."""

from collections.abc import Sequence
from dataclasses import dataclass, replace

from carmen.application.context import Requester
from carmen.application.ports.embeddings import Vector
from carmen.application.ports.repositories import (
    AgentLifecycleEntry,
    ConversationThread,
    Feedback,
    FeedbackOutcome,
    GapCluster,
    GapDraft,
    GapFilter,
    GapId,
    GapStatus,
    GlossaryAction,
    GlossaryChange,
    GlossaryTerm,
    KnowledgeChunk,
    LifecycleChange,
    MemoryExample,
    MemoryExampleDraft,
    MemoryId,
    NewConversation,
    NewMessage,
    NewToolCall,
    SituationBrief,
    ThreadMessage,
    Topic,
    TopicId,
    TopicStatus,
)
from carmen.application.ports.system import IdGenerator
from carmen.domain.agents.card import AgentLifecycleState
from carmen.domain.approval.models import ApprovalRecord, ApprovalStatus, HumanApprovalRequest
from carmen.domain.conversation.turn import ConversationTurn
from carmen.domain.delegation.models import AgentResult
from carmen.domain.errors import InvalidTransitionError, ValidationError
from carmen.domain.ids import AgentId, ApprovalId, ConversationId, MessageId, PrincipalId, TurnId
from carmen.domain.locale import Locale
from carmen.domain.plan.models import QueryPlan
from carmen.domain.time import Instant
from support.fakes.embeddings import cosine
from support.fakes.system import SeqIdGenerator

# --- Conversaciones y turnos ---


class InMemoryConversationRepository:
    def __init__(self) -> None:
        self.conversations: dict[ConversationId, NewConversation] = {}
        self.updated_at: dict[ConversationId, Instant] = {}
        self.messages: dict[ConversationId, list[NewMessage]] = {}
        self.tool_calls: dict[MessageId, tuple[NewToolCall, ...]] = {}
        self.feedback: dict[tuple[MessageId, PrincipalId], Feedback] = {}

    async def create(self, c: NewConversation) -> ConversationId:
        if c.conversation_id in self.conversations:
            msg = f"la conversación {c.conversation_id} ya existe"
            raise ValidationError(msg)
        self.conversations[c.conversation_id] = c
        self.updated_at[c.conversation_id] = c.created_at
        self.messages[c.conversation_id] = []
        return c.conversation_id

    async def append_message(self, m: NewMessage, calls: Sequence[NewToolCall]) -> MessageId:
        # Se valida todo antes de escribir nada: o se guardan juntos, o ninguno.
        if m.conversation_id not in self.conversations:
            msg = f"la conversación {m.conversation_id} no existe"
            raise ValidationError(msg)
        if any(c.message_id != m.message_id for c in calls):
            msg = "toda llamada pertenece al mensaje con el que se guarda"
            raise ValidationError(msg)
        if m.message_id in self.tool_calls:
            msg = f"el mensaje {m.message_id} ya existe"
            raise ValidationError(msg)
        self.messages[m.conversation_id].append(m)
        self.tool_calls[m.message_id] = tuple(calls)
        return m.message_id

    async def touch(self, cid: ConversationId, at: Instant) -> None:
        if cid in self.updated_at:
            self.updated_at[cid] = max(self.updated_at[cid], at)

    async def get_thread(
        self, cid: ConversationId, requester: Requester
    ) -> ConversationThread | None:
        conversation = self.conversations.get(cid)
        if conversation is None or conversation.owner != requester.principal_id:
            return None
        return ConversationThread(
            conversation_id=cid,
            owner=conversation.owner,
            locale=conversation.locale,
            title=conversation.title,
            messages=tuple(
                ThreadMessage(m.message_id, m.role, m.content, m.status, m.created_at)
                for m in self.messages[cid]
            ),
        )

    async def record_feedback(self, f: Feedback) -> FeedbackOutcome:
        key = (f.message_id, f.principal_id)
        previous = self.feedback.get(key)
        self.feedback[key] = f
        if previous is None:
            return FeedbackOutcome.CREATED
        if (previous.rating, previous.comment) == (f.rating, f.comment):
            self.feedback[key] = previous
            return FeedbackOutcome.UNCHANGED
        return FeedbackOutcome.UPDATED


class InMemoryTurnRepository:
    def __init__(self) -> None:
        self.turns: dict[TurnId, ConversationTurn] = {}
        self.messages: dict[TurnId, MessageId] = {}

    async def save(
        self,
        turn: ConversationTurn,
        *,
        message_id: MessageId,
        results: Sequence[AgentResult] = (),
    ) -> None:
        if turn.turn_id in self.turns:
            msg = f"el turno {turn.turn_id} ya está registrado y no se reescribe"
            raise ValidationError(msg)
        if tuple(r.run for r in results) != turn.runs:
            msg = "los resultados no corresponden a las ejecuciones del turno, en su orden"
            raise ValidationError(msg)
        self.turns[turn.turn_id] = turn
        self.messages[turn.turn_id] = message_id

    async def get(self, turn_id: TurnId) -> ConversationTurn | None:
        return self.turns.get(turn_id)


# --- Memoria, lagunas, corpus y brief ---


@dataclass(frozen=True, slots=True)
class _StoredExample:
    memory_id: MemoryId
    question: str
    embedding: Vector
    plan: QueryPlan
    locale: Locale
    hits: int
    active: bool


class InMemoryMemoryRepository:
    def __init__(self, ids: IdGenerator | None = None) -> None:
        self._ids = ids or SeqIdGenerator()
        self.examples: dict[tuple[str, Locale], _StoredExample] = {}

    async def similar_plans(self, v: Vector, k: int, min_sim: float) -> list[MemoryExample]:
        scored = [(cosine(v, e.embedding), e) for e in self.examples.values() if e.active]
        hits = sorted((s for s in scored if s[0] >= min_sim), key=lambda s: (-s[0], s[1].memory_id))
        return [
            MemoryExample(e.memory_id, e.question, e.plan, e.locale, similarity, e.hits)
            for similarity, e in hits[:k]
        ]

    async def upsert_example(self, e: MemoryExampleDraft) -> MemoryId:
        key = (e.question_norm, e.locale)
        current = self.examples.get(key)
        if current is None:
            memory_id = MemoryId(f"mem_{self._ids.new_id()}")
            self.examples[key] = _StoredExample(
                memory_id, e.question, e.embedding, e.plan, e.locale, hits=1, active=True
            )
            return memory_id
        self.examples[key] = replace(current, plan=e.plan, hits=current.hits + 1, active=True)
        return current.memory_id

    async def deactivate(self, mid: MemoryId, by: PrincipalId) -> None:
        for key, example in self.examples.items():
            if example.memory_id == mid:
                self.examples[key] = replace(example, active=False)
                return
        msg = f"el ejemplo {mid} no existe"
        raise ValidationError(msg)


@dataclass(frozen=True, slots=True)
class _StoredGap:
    gap_id: GapId
    question: str
    locale: Locale
    occurrences: int
    status: GapStatus
    last_seen: Instant
    cluster_name: str | None = None


class InMemoryGapRepository:
    def __init__(self, ids: IdGenerator | None = None) -> None:
        self._ids = ids or SeqIdGenerator()
        self.gaps: dict[tuple[str, Locale], _StoredGap] = {}

    async def record(self, g: GapDraft) -> GapId:
        key = (g.question_norm, g.locale)
        current = self.gaps.get(key)
        if current is None:
            gap_id = GapId(f"gap_{self._ids.new_id()}")
            self.gaps[key] = _StoredGap(gap_id, g.question, g.locale, 1, GapStatus.OPEN, g.at)
            return gap_id
        self.gaps[key] = replace(
            current, occurrences=current.occurrences + 1, last_seen=max(current.last_seen, g.at)
        )
        return current.gap_id

    async def list_clusters(self, f: GapFilter) -> list[GapCluster]:
        selected = [
            g
            for g in self.gaps.values()
            if (f.status is None or g.status is f.status)
            and (f.locale is None or g.locale is f.locale)
            and g.occurrences >= f.min_occurrences
        ]
        selected.sort(key=lambda g: (-g.occurrences, g.gap_id))
        return [
            GapCluster(g.cluster_name, g.locale, (g.question,), g.occurrences, g.last_seen)
            for g in selected[: f.limit]
        ]


@dataclass(frozen=True, slots=True)
class StoredChunk:
    source: str
    chunk_ix: int
    title: str
    content: str
    embedding: Vector


class InMemoryKnowledgeRepository:
    def __init__(self, chunks: Sequence[StoredChunk] = ()) -> None:
        self.chunks = tuple(chunks)

    async def search(self, v: Vector, k: int, min_sim: float) -> list[KnowledgeChunk]:
        scored = [(cosine(v, c.embedding), c) for c in self.chunks]
        above = sorted(
            (s for s in scored if s[0] >= min_sim),
            key=lambda s: (-s[0], s[1].source, s[1].chunk_ix),
        )
        return [
            KnowledgeChunk(c.source, c.chunk_ix, c.title, c.content, similarity)
            for similarity, c in above[:k]
        ]


class InMemoryBriefRepository:
    def __init__(self, brief: SituationBrief | None = None) -> None:
        self.brief = brief

    async def get(self) -> SituationBrief | None:
        return self.brief

    async def put(self, b: SituationBrief) -> None:
        self.brief = b


# --- Glosario y temas ---


class InMemoryGlossaryRepository:
    def __init__(self, terms: Sequence[GlossaryTerm] = ()) -> None:
        self.terms = {t.term: t for t in terms}
        self.changes: list[GlossaryChange] = []

    async def list_active(self) -> tuple[GlossaryTerm, ...]:
        return tuple(sorted((t for t in self.terms.values() if t.active), key=lambda t: t.term))

    async def get(self, term: str) -> GlossaryTerm | None:
        return self.terms.get(term)

    async def upsert(self, t: GlossaryTerm, actor: PrincipalId, at: Instant) -> GlossaryChange:
        before = self.terms.get(t.term)
        action = GlossaryAction.CREATE if before is None else GlossaryAction.UPDATE
        change = GlossaryChange(t.term, action, actor, at, before=before, after=t)
        self.terms[t.term] = t
        self.changes.append(change)
        return change

    async def deactivate(self, term: str, actor: PrincipalId, at: Instant) -> GlossaryChange:
        before = self.terms.get(term)
        if before is None or not before.active:
            msg = f"el término {term!r} no existe o ya está inactivo"
            raise ValidationError(msg)
        after = replace(before, active=False)
        change = GlossaryChange(term, GlossaryAction.DEACTIVATE, actor, at, before, after)
        self.terms[term] = after
        self.changes.append(change)
        return change

    async def history(self, term: str) -> tuple[GlossaryChange, ...]:
        return tuple(c for c in self.changes if c.term == term)


class InMemoryTopicRepository:
    def __init__(self) -> None:
        self.topics: dict[TopicId, Topic] = {}

    async def upsert(self, t: Topic) -> None:
        self.topics[t.topic_id] = t

    async def list_by_demand(self, limit: int) -> list[Topic]:
        return sorted(self.topics.values(), key=lambda t: (-t.asked, t.topic_id))[:limit]

    async def set_status(self, tid: TopicId, status: TopicStatus, at: Instant) -> Topic:
        topic = self.topics.get(tid)
        if topic is None:
            msg = f"el tema {tid} no existe"
            raise ValidationError(msg)
        updated = replace(topic, status=status)
        self.topics[tid] = updated
        return updated


# --- Aprobaciones y ciclo de vida ---


class InMemoryApprovalRepository:
    def __init__(self) -> None:
        self.requests: dict[ApprovalId, HumanApprovalRequest] = {}
        self.records: dict[ApprovalId, ApprovalRecord] = {}

    async def create(self, request: HumanApprovalRequest) -> ApprovalRecord:
        if request.request_id in self.requests:
            msg = f"la aprobación {request.request_id} ya existe"
            raise ValidationError(msg)
        record = ApprovalRecord(request.request_id, ApprovalStatus.PENDING, request.evidence_refs)
        self.requests[request.request_id] = request
        self.records[request.request_id] = record
        return record

    async def get(self, request_id: ApprovalId) -> ApprovalRecord | None:
        return self.records.get(request_id)

    async def decide(
        self, request_id: ApprovalId, status: ApprovalStatus, by: PrincipalId, at: Instant
    ) -> ApprovalRecord:
        record = self.records.get(request_id)
        if record is None:
            msg = f"la aprobación {request_id} no existe"
            raise ValidationError(msg)
        if status not in (ApprovalStatus.APPROVED, ApprovalStatus.REJECTED):
            msg = f"una persona aprueba o rechaza; {status} no es una decisión"
            raise InvalidTransitionError(msg)
        if (
            record.status is not ApprovalStatus.PENDING
            or at >= self.requests[request_id].expires_at
        ):
            msg = f"{request_id} ya no está pendiente"
            raise InvalidTransitionError(msg)
        decided = replace(record, status=status, decided_by=by, decided_at=at)
        self.records[request_id] = decided
        return decided

    async def expire_due(self, now: Instant) -> tuple[ApprovalId, ...]:
        due = tuple(
            sorted(
                rid
                for rid, record in self.records.items()
                if record.status is ApprovalStatus.PENDING and self.requests[rid].expires_at <= now
            )
        )
        for rid in due:
            self.records[rid] = replace(self.records[rid], status=ApprovalStatus.EXPIRED)
        return due


class InMemoryAgentLifecycleRepository:
    def __init__(self) -> None:
        self.entries: dict[AgentId, AgentLifecycleEntry] = {}
        self.changes: list[LifecycleChange] = []

    async def register(self, entry: AgentLifecycleEntry, actor: PrincipalId) -> None:
        if entry.agent_id in self.entries:
            msg = f"{entry.agent_id} ya está registrado"
            raise ValidationError(msg)
        if entry.state is not AgentLifecycleState.DISCOVERED:
            msg = "un agente nuevo entra en DISCOVERED (7.11.2)"
            raise InvalidTransitionError(msg)
        self.entries[entry.agent_id] = entry
        self.changes.append(
            LifecycleChange(entry.agent_id, None, entry.state, "alta", actor, entry.updated_at)
        )

    async def get(self, agent_id: AgentId) -> AgentLifecycleEntry | None:
        return self.entries.get(agent_id)

    async def transition(
        self, entry: AgentLifecycleEntry, reason: str, actor: PrincipalId
    ) -> LifecycleChange:
        current = self.entries.get(entry.agent_id)
        if current is None:
            msg = f"{entry.agent_id} no está registrado"
            raise ValidationError(msg)
        if not current.state.can_transition_to(entry.state):
            msg = f"{entry.agent_id}: {current.state} -> {entry.state} no está en 7.11.2"
            raise InvalidTransitionError(msg)
        change = LifecycleChange(
            entry.agent_id, current.state, entry.state, reason, actor, entry.updated_at
        )
        self.entries[entry.agent_id] = entry
        self.changes.append(change)
        return change

    async def history(self, agent_id: AgentId) -> tuple[LifecycleChange, ...]:
        return tuple(reversed([c for c in self.changes if c.agent_id == agent_id]))
