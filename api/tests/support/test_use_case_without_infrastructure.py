"""Prompt 5: un caso de uso completo se escribe contra los puertos y se prueba sin infraestructura.

`delegate` es un caso de uso mínimo de delegación: guarda la pregunta, comprueba la política por
agente, ejecuta las tareas, emite los eventos del turno, guarda la respuesta y el turno. Solo
conoce los protocolos de application/ports; la prueba le pasa los dobles en memoria.
"""

import asyncio
from collections.abc import Coroutine
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

import pytest

from carmen.application.context import ExecutionContext
from carmen.application.errors import AgentUnavailableError
from carmen.application.events import (
    AgentResultPayload,
    DelegationPayload,
    DomainEvent,
    DonePayload,
    EventPayload,
    EventType,
    ModePayload,
    WarningPayload,
)
from carmen.application.ports.agents import AgentRunnerPort
from carmen.application.ports.policy import PolicyPort
from carmen.application.ports.repositories import (
    ConversationRepository,
    MessageRole,
    NewConversation,
    NewMessage,
    TurnRepository,
)
from carmen.application.ports.system import Clock, EventSink, IdGenerator
from carmen.domain.conversation.turn import ConversationTurn, TokenUsage, TurnStatus
from carmen.domain.delegation.models import AgentResult, AgentResultStatus, DelegationPlan
from carmen.domain.errors import ValidationError
from carmen.domain.ids import AgentId, MessageId, RoleId, Scope
from carmen.domain.policy.models import (
    AgentAction,
    AssignmentSource,
    Effect,
    PolicyRole,
    RoleAgentGrant,
    RoleAssignment,
)
from support.builders import (
    CONVERSATION,
    CORRELATION,
    MESSAGE,
    PLENDATA,
    POLICY_VERSION,
    PRINCIPAL,
    TURN,
    VIGIA,
    agent_result,
    agent_task,
    delegation_plan,
    execution_context,
    requester,
)
from support.fakes import (
    FakeAgentRunner,
    FrozenClock,
    InMemoryConversationRepository,
    InMemoryPolicy,
    InMemoryTurnRepository,
    ListEventSink,
    SeqIdGenerator,
)

pytestmark = pytest.mark.application


@dataclass(frozen=True, slots=True)
class Ports:
    clock: Clock
    ids: IdGenerator
    events: EventSink
    policy: PolicyPort
    agents: AgentRunnerPort
    conversations: ConversationRepository
    turns: TurnRepository


class _Emitter:
    def __init__(self, ports: Ports, ctx: ExecutionContext) -> None:
        self._ports, self._ctx, self._sequence = ports, ctx, 0

    async def __call__(self, payload: EventPayload) -> None:
        self._sequence += 1
        event = DomainEvent(
            self._ctx.correlation_id, self._sequence, self._ports.clock.now(), payload
        )
        await self._ports.events.emit(event)


async def delegate(
    question: str, plan: DelegationPlan, ctx: ExecutionContext, ports: Ports
) -> ConversationTurn:
    emit = _Emitter(ports, ctx)
    await ports.conversations.create(
        NewConversation(ctx.conversation_id, ctx.requester.principal_id, ctx.locale, ctx.started_at)
    )
    await ports.conversations.append_message(
        NewMessage(
            ctx.message_id,
            ctx.conversation_id,
            MessageRole.USER,
            question,
            TurnStatus.COMPLETED,
            ctx.correlation_id,
            ctx.started_at,
            ctx.locale,
        ),
        [],
    )
    await emit(ModePayload(plan.response_mode))

    results: list[AgentResult] = []
    missing: list[AgentId] = []
    for task in plan.tasks:
        decision = await ports.policy.decide(
            principal_id=plan.principal_id,
            action=AgentAction.INVOKE,
            agent_id=task.agent_id,
            turn_id=plan.turn_id,
        )
        if not decision.allowed:
            missing.append(task.agent_id)
            continue
        await emit(DelegationPayload(task.task_id, task.agent_id, task.depends_on))
        try:
            result = await ports.agents.run(task, ctx)
        except AgentUnavailableError as error:
            missing.append(task.agent_id)
            await emit(WarningPayload(error.code, str(error), agent_id=task.agent_id))
            continue
        results.append(result)
        await emit(
            AgentResultPayload(
                task_id=task.task_id,
                agent_id=task.agent_id,
                status=result.status,
                evidence_count=len(result.evidence),
                ms=result.run.duration_ms,
            )
        )

    finished = ports.clock.now()
    latency_ms = int((finished.at - ctx.started_at.at).total_seconds() * 1000)
    partial = bool(missing) or any(r.status is not AgentResultStatus.OK for r in results)
    status = TurnStatus.PARTIAL if partial else TurnStatus.COMPLETED
    turn = ConversationTurn(
        turn_id=plan.turn_id,
        conversation_id=ctx.conversation_id,
        principal_id=plan.principal_id,
        question=question,
        response_mode=plan.response_mode,
        policy_version=plan.policy_version,
        status=status,
        agents_used=tuple(sorted({r.agent_id for r in results} | set(missing))),
        delegation_plan=plan,
        runs=tuple(r.run for r in results),
        evidence=tuple(item for r in results for item in r.evidence),
        tokens=TokenUsage(
            tokens_in=sum(r.run.tokens_in for r in results),
            tokens_out=sum(r.run.tokens_out for r in results),
        ),
        cost_eur=sum((r.run.cost_eur for r in results), start=Decimal(0)),
        latency_ms=latency_ms,
        missing_agents=tuple(missing),
    )
    answer = MessageId(f"msg_{ports.ids.new_id()}")
    await ports.conversations.append_message(
        NewMessage(
            answer,
            ctx.conversation_id,
            MessageRole.ASSISTANT,
            f"{len(turn.evidence)} hechos de {len(results)} agentes.",
            status,
            ctx.correlation_id,
            finished,
            ctx.locale,
        ),
        [],
    )
    await ports.turns.save(turn, message_id=answer, results=results)
    await emit(
        DonePayload(
            message_id=answer,
            conversation_id=ctx.conversation_id,
            status=status,
            partial=partial,
            missing_systems=(),
            grounding_ok=None,
            plan_id=plan.plan_id,
            round=1,
            repairs=0,
            latency_ms=latency_ms,
            model=ctx.llm.model,
            catalog_versions=ctx.catalog_versions,
            response_mode=plan.response_mode,
            agents_used=turn.agents_used,
            missing_agents=turn.missing_agents,
        )
    )
    return turn


# --- La prueba: todo en memoria, el mismo resultado en cada ejecución ---

ANALYST = RoleId("analista")


def run[T](coro: Coroutine[object, object, T]) -> T:
    return asyncio.run(coro)


def policy(clock: Clock, *, plendata: Effect | None = Effect.ALLOW) -> InMemoryPolicy:
    grants = [
        RoleAgentGrant(
            ANALYST,
            VIGIA,
            frozenset({AgentAction.INVOKE}),
            Effect.ALLOW,
            frozenset({Scope("vigia.read")}),
        )
    ]
    if plendata is not None:
        grants.append(RoleAgentGrant(ANALYST, PLENDATA, frozenset({AgentAction.INVOKE}), plendata))
    return InMemoryPolicy(
        version=POLICY_VERSION,
        roles=[PolicyRole(ANALYST, "Analista", frozenset(), "1")],
        assignments=[RoleAssignment(PRINCIPAL, ANALYST, AssignmentSource.DIRECTORY)],
        grants=grants,
        clock=clock,
    )


@dataclass(frozen=True, slots=True)
class World:
    ports: Ports
    sink: ListEventSink
    runner: FakeAgentRunner
    conversations: InMemoryConversationRepository
    turns: InMemoryTurnRepository


def world(runner: FakeAgentRunner, *, plendata: Effect | None = Effect.ALLOW) -> World:
    clock = FrozenClock(tick=timedelta(milliseconds=250))
    sink = ListEventSink()
    conversations = InMemoryConversationRepository()
    turns = InMemoryTurnRepository()
    ports = Ports(
        clock=clock,
        ids=SeqIdGenerator(),
        events=sink,
        policy=policy(clock, plendata=plendata),
        agents=runner,
        conversations=conversations,
        turns=turns,
    )
    return World(ports, sink, runner, conversations, turns)


VIGIA_TASK = agent_task(1, VIGIA)
PLENDATA_TASK = agent_task(2, PLENDATA, objective="ventas por estación del mes en curso")
PLAN = delegation_plan(VIGIA_TASK, PLENDATA_TASK)
QUESTION = "¿Qué estaciones con alarmas venden menos?"


def both_agents() -> FakeAgentRunner:
    return FakeAgentRunner({VIGIA: agent_result(VIGIA_TASK), PLENDATA: agent_result(PLENDATA_TASK)})


def test_a_delegated_turn_runs_end_to_end_in_memory() -> None:
    w = world(both_agents())
    turn = run(delegate(QUESTION, PLAN, execution_context(), w.ports))

    assert turn.status is TurnStatus.COMPLETED
    assert turn.agents_used == (PLENDATA, VIGIA)
    assert turn.missing_agents == ()
    assert len(turn.evidence) == 2
    assert w.runner.tasks == [VIGIA_TASK, PLENDATA_TASK]
    assert run(w.turns.get(TURN)) == turn

    thread = run(w.conversations.get_thread(CONVERSATION, requester()))
    assert thread is not None
    assert [m.role for m in thread.messages] == [MessageRole.USER, MessageRole.ASSISTANT]
    assert thread.messages[0].message_id == MESSAGE
    assert thread.messages[1].content == "2 hechos de 2 agentes."

    assert w.sink.types() == [
        EventType.MODE,
        EventType.DELEGATION,
        EventType.AGENT_RESULT,
        EventType.DELEGATION,
        EventType.AGENT_RESULT,
        EventType.DONE,
    ]
    assert [e.sequence for e in w.sink.events] == list(range(1, 7))
    assert {e.correlation_id for e in w.sink.events} == {CORRELATION}
    instants = [e.occurred_at.at for e in w.sink.events]
    assert instants == sorted(instants)
    done = w.sink.events[-1].payload
    assert isinstance(done, DonePayload)
    assert done.plan_id == PLAN.plan_id
    assert done.message_id == MessageId("msg_000000000001")
    assert done.latency_ms == turn.latency_ms


def test_the_same_inputs_give_the_same_turn_and_events() -> None:
    first, second = world(both_agents()), world(both_agents())
    turn_a = run(delegate(QUESTION, PLAN, execution_context(), first.ports))
    turn_b = run(delegate(QUESTION, PLAN, execution_context(), second.ports))
    assert turn_a == turn_b
    assert first.sink.events == second.sink.events


def test_an_agent_without_grant_is_missing_and_never_runs() -> None:
    w = world(both_agents(), plendata=None)
    turn = run(delegate(QUESTION, PLAN, execution_context(), w.ports))

    assert w.runner.tasks == [VIGIA_TASK]
    assert turn.status is TurnStatus.PARTIAL
    assert turn.missing_agents == (PLENDATA,)
    done = w.sink.events[-1].payload
    assert isinstance(done, DonePayload)
    assert done.partial
    assert done.missing_agents == (PLENDATA,)


def test_an_unavailable_agent_degrades_the_turn_with_a_warning() -> None:
    w = world(FakeAgentRunner({VIGIA: agent_result(VIGIA_TASK)}))
    turn = run(delegate(QUESTION, PLAN, execution_context(), w.ports))

    assert turn.status is TurnStatus.PARTIAL
    assert turn.missing_agents == (PLENDATA,)
    warnings = [e.payload for e in w.sink.events if isinstance(e.payload, WarningPayload)]
    assert [(p.code, p.agent_id) for p in warnings] == [("mcp_unavailable", PLENDATA)]
    assert run(w.turns.get(TURN)) == turn


def test_a_turn_is_never_written_twice() -> None:
    w = world(both_agents())
    run(delegate(QUESTION, PLAN, execution_context(), w.ports))
    with pytest.raises(ValidationError, match="ya existe"):
        run(delegate(QUESTION, PLAN, execution_context(), w.ports))
