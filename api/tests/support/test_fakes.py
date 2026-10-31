"""Prompt 5: los dobles cumplen las garantías que declara cada puerto."""

import asyncio
from collections.abc import Coroutine
from dataclasses import replace
from datetime import timedelta

import pytest

from carmen.application.context import UserToken
from carmen.application.errors import (
    AgentContractViolationError,
    AgentUnavailableError,
    ClassificationDeniedError,
    EgressDomainNotAllowedError,
    EmbeddingDimensionMismatchError,
    IdentityRejectedError,
    IdentityUnavailableError,
    LlmMalformedOutputError,
    McpToolError,
    ProviderNotBoundError,
)
from carmen.application.events import DomainEvent, ModePayload
from carmen.application.ports.egress import Url
from carmen.application.ports.identity import Audience
from carmen.application.ports.llm import LlmMessage, LlmRole, LlmStructuredResult, RequestId
from carmen.application.ports.mcp import HealthStatus, ToolDescriptor, ToolInvocation
from carmen.application.ports.model_provider import ModelPayload
from carmen.application.ports.repositories import (
    AgentLifecycleEntry,
    Feedback,
    FeedbackOutcome,
    GapDraft,
    GapFilter,
    GlossaryAction,
    GlossaryTerm,
    MemoryExampleDraft,
    MessageRole,
    NewConversation,
    NewMessage,
    NewToolCall,
    Rating,
    SituationBrief,
    Topic,
    TopicId,
    TopicStatus,
)
from carmen.domain.agents.card import AgentLifecycleState
from carmen.domain.approval.models import ApprovalStatus, HumanApprovalRequest, Impact
from carmen.domain.conversation.turn import TokenUsage, TurnStatus
from carmen.domain.delegation.models import AgentResultStatus
from carmen.domain.egress.models import DataClass, Purpose
from carmen.domain.errors import (
    InvalidTransitionError,
    LlmUnavailableError,
    McpUnavailableError,
    ValidationError,
)
from carmen.domain.ids import (
    AgentId,
    ApprovalId,
    CallId,
    MessageId,
    PrincipalId,
    ProviderId,
    RoleId,
    Scope,
    StepId,
)
from carmen.domain.locale import Locale
from carmen.domain.orchestration.mode import ResponseMode
from carmen.domain.policy.models import (
    AgentAction,
    AssignmentSource,
    Effect,
    PlatformAction,
    PolicyRole,
    RoleAgentGrant,
    RoleAssignment,
)
from carmen.domain.role import Role
from carmen.domain.system import SystemId
from support.builders import (
    CONVERSATION,
    CORRELATION,
    PLENDATA,
    PRINCIPAL,
    TURN,
    VIGIA,
    VIGIA_SYSTEM,
    agent_result,
    agent_task,
    at,
    direct_turn,
    envelope,
    evidence_fact,
    execution_context,
    query_plan,
    requester,
)
from support.fakes import (
    FakeAgentRunner,
    FakeEgress,
    FakeEmbeddingAdapter,
    FakeLlmAdapter,
    FakeMcpClient,
    FakeModelProvider,
    FakeTokenExchange,
    InMemoryAgentLifecycleRepository,
    InMemoryApprovalRepository,
    InMemoryBriefRepository,
    InMemoryConversationRepository,
    InMemoryGapRepository,
    InMemoryGlossaryRepository,
    InMemoryKnowledgeRepository,
    InMemoryMemoryRepository,
    InMemoryPolicy,
    InMemoryTopicRepository,
    InMemoryTurnRepository,
    ListEventSink,
)
from support.fakes.embeddings import cosine, deterministic_vector
from support.fakes.repositories import StoredChunk

pytestmark = pytest.mark.application


def run[T](coro: Coroutine[object, object, T]) -> T:
    return asyncio.run(coro)


CTX = execution_context()
OTHER = PrincipalId("usr_b22c")
ANALYST, AUDITOR, ADMIN = RoleId("analista"), RoleId("auditor"), RoleId("carmen-admin")


# --- Política en memoria (7.9.3, 7.9.4, 7.9.5) ---


def policy() -> InMemoryPolicy:
    return InMemoryPolicy(
        version="pol-2026-07-21",
        roles=[
            PolicyRole(ANALYST, "Analista", frozenset(), "1"),
            PolicyRole(AUDITOR, "Auditor", frozenset({PlatformAction.AUDIT_READ}), "1"),
            PolicyRole(ADMIN, "Admin", frozenset({PlatformAction.CARMEN_ADMIN}), "1"),
        ],
        assignments=[
            RoleAssignment(PRINCIPAL, ANALYST, AssignmentSource.DIRECTORY),
            RoleAssignment(PRINCIPAL, AUDITOR, AssignmentSource.MANUAL),
            RoleAssignment(OTHER, ADMIN, AssignmentSource.MANUAL),
        ],
        grants=[
            RoleAgentGrant(
                ANALYST,
                VIGIA,
                frozenset(AgentAction),
                Effect.ALLOW,
                frozenset({Scope("vigia.read")}),
            ),
            RoleAgentGrant(
                AUDITOR,
                VIGIA,
                frozenset({AgentAction.INVOKE}),
                Effect.ALLOW,
                frozenset({Scope("vigia.audit")}),
            ),
            RoleAgentGrant(ANALYST, PLENDATA, frozenset({AgentAction.DISCOVER}), Effect.ALLOW),
            RoleAgentGrant(
                AUDITOR,
                PLENDATA,
                frozenset({AgentAction.INVOKE}),
                Effect.DENY,
                reason="separación de funciones",
            ),
            RoleAgentGrant(ANALYST, PLENDATA, frozenset({AgentAction.INVOKE}), Effect.ALLOW),
        ],
    )


def decide(principal: PrincipalId, agent: AgentId, action: AgentAction) -> tuple[bool, str]:
    d = run(policy().decide(principal_id=principal, action=action, agent_id=agent, turn_id=TURN))
    assert d.policy_version == "pol-2026-07-21"
    return d.allowed, d.reason_code


def test_allow_unites_scopes_of_every_role() -> None:
    d = run(
        policy().decide(
            principal_id=PRINCIPAL, action=AgentAction.INVOKE, agent_id=VIGIA, turn_id=TURN
        )
    )
    assert d.allowed
    assert d.scopes == {Scope("vigia.read"), Scope("vigia.audit")}


def test_explicit_deny_wins_over_any_allow() -> None:
    assert decide(PRINCIPAL, PLENDATA, AgentAction.INVOKE) == (False, "explicit_deny")
    assert decide(PRINCIPAL, PLENDATA, AgentAction.DISCOVER) == (True, "grant")


def test_unknown_and_hidden_agents_get_the_same_denial() -> None:
    hidden = AgentId("agent.plenlegal")
    missing = AgentId("agent.no-existe")
    assert decide(PRINCIPAL, hidden, AgentAction.DISCOVER) == decide(
        PRINCIPAL, missing, AgentAction.DISCOVER
    )
    assert decide(PRINCIPAL, missing, AgentAction.DISCOVER) == (False, "no_grant")


def test_administering_is_not_accessing() -> None:
    assert decide(OTHER, VIGIA, AgentAction.INVOKE) == (False, "no_grant")
    admin = run(
        policy().decide_platform(
            principal_id=OTHER, action=PlatformAction.CARMEN_ADMIN, turn_id=TURN
        )
    )
    assert admin.allowed
    assert admin.agent_id is None
    no_audit = run(
        policy().decide_platform(principal_id=OTHER, action=PlatformAction.AUDIT_READ, turn_id=TURN)
    )
    assert (no_audit.allowed, no_audit.reason_code) == (False, "no_role")


def test_allowed_agents_lists_only_granted_ones_in_order() -> None:
    allowed = run(
        policy().allowed_agents(principal_id=PRINCIPAL, action=AgentAction.INVOKE, turn_id=TURN)
    )
    assert [d.agent_id for d in allowed] == [VIGIA]
    nobody = run(
        policy().allowed_agents(
            principal_id=PrincipalId("usr_none"), action=AgentAction.DISCOVER, turn_id=TURN
        )
    )
    assert nobody == ()


# --- Agentes, MCP, identidad, salida y proveedores ---


def test_agent_runner_follows_its_script_and_records_tasks() -> None:
    task = agent_task()
    runner = FakeAgentRunner({VIGIA: lambda t: agent_result(t)})
    result = run(runner.run(task, CTX))
    assert result.status is AgentResultStatus.OK
    assert runner.tasks == [task]


def test_agent_runner_fails_like_the_port_says() -> None:
    task = agent_task(2, PLENDATA)
    with pytest.raises(AgentUnavailableError):
        run(FakeAgentRunner({}).run(task, CTX))
    wrong = FakeAgentRunner({PLENDATA: agent_result(agent_task(1, PLENDATA))})
    with pytest.raises(AgentContractViolationError):
        run(wrong.run(task, CTX))
    broken = FakeAgentRunner({PLENDATA: AgentUnavailableError("caído")})
    with pytest.raises(AgentUnavailableError, match="caído"):
        run(broken.run(task, CTX))


def _invocation(tool: str = "query_metric") -> ToolInvocation:
    token = run(
        FakeTokenExchange().exchange(
            user_token=UserToken("t"), audience=Audience("api://vigia"), scopes=[]
        )
    )
    return ToolInvocation(
        CallId("cal_1"), StepId("s1"), VIGIA_SYSTEM, tool, {"metric": "monitores_ko"}, token
    )


def test_mcp_client_returns_scripted_envelopes() -> None:
    descriptor = ToolDescriptor(VIGIA_SYSTEM, "query_metric", "consulta una métrica", {}, "v1")
    client = FakeMcpClient(
        tools={VIGIA_SYSTEM: [descriptor]},
        responses={(VIGIA_SYSTEM, "query_metric"): envelope()},
    )
    assert run(client.list_tools(VIGIA_SYSTEM, CTX)) == [descriptor]
    assert run(client.call_tool(_invocation(), CTX)).facts[0].value == 4
    assert run(client.health(VIGIA_SYSTEM)).status is HealthStatus.UP
    with pytest.raises(McpToolError):
        run(client.call_tool(_invocation("top_n"), CTX))
    assert len(client.calls) == 2


def test_mcp_client_down_system() -> None:
    client = FakeMcpClient(tools={VIGIA_SYSTEM: []}, responses={}, down=frozenset({VIGIA_SYSTEM}))
    with pytest.raises(McpUnavailableError):
        run(client.list_tools(VIGIA_SYSTEM, CTX))
    with pytest.raises(McpUnavailableError):
        run(client.call_tool(_invocation(), CTX))
    assert run(client.health(SystemId("plendata"))).status is HealthStatus.DOWN


def test_token_exchange_never_records_or_prints_the_token() -> None:
    exchange = FakeTokenExchange(ttl=timedelta(minutes=1))
    token = run(
        exchange.exchange(
            user_token=UserToken("secreto-de-usuario"),
            audience=Audience("api://vigia"),
            scopes=[Scope("vigia.read")],
        )
    )
    assert "secreto" not in repr(token) + str(token) + repr(exchange.exchanges)
    assert token.valid_at(at(59))
    assert not token.valid_at(at(60))
    assert "secreto" not in repr(UserToken("secreto")) + str(UserToken("secreto"))


def test_token_exchange_failures() -> None:
    audience = Audience("api://plendata")
    with pytest.raises(IdentityRejectedError):
        run(
            FakeTokenExchange(rejected=frozenset({audience})).exchange(
                user_token=UserToken("t"), audience=audience, scopes=[]
            )
        )
    with pytest.raises(IdentityUnavailableError):
        run(
            FakeTokenExchange(available=False).exchange(
                user_token=UserToken("t"), audience=audience, scopes=[]
            )
        )


def test_egress_denies_everything_before_connecting() -> None:
    egress = FakeEgress()
    with pytest.raises(EgressDomainNotAllowedError, match=r"boe\.es"):
        run(
            egress.fetch(
                agent_id=AgentId("agent.plenlegal"),
                url=Url("https://boe.es/diario"),
                purpose=Purpose.ANALYSIS,
                classification=DataClass.PUBLICO,
                ctx=CTX,
            )
        )
    assert len(egress.attempts) == 1


def test_model_provider_requires_a_binding_and_a_fitting_classification() -> None:
    legal, ext = AgentId("agent.plenlegal"), ProviderId("provider.ext-llm")
    provider = FakeModelProvider(bindings={(legal, ext): DataClass.INTERNO})
    payload = ModelPayload("ext-1", Purpose.ANALYSIS, (LlmMessage(LlmRole.USER, "resume"),), 200)

    def call(agent: AgentId, data: DataClass) -> object:
        return run(
            provider.complete(
                agent_id=agent, provider=ext, payload=payload, classification=data, ctx=CTX
            )
        )

    output = call(legal, DataClass.PUBLICO)
    assert getattr(output, "provider", None) == ext
    with pytest.raises(ClassificationDeniedError):
        call(legal, DataClass.CONFIDENCIAL)
    with pytest.raises(ProviderNotBoundError):
        call(VIGIA, DataClass.PUBLICO)


def test_llm_script_and_its_failures() -> None:
    result = LlmStructuredResult("hola", (), TokenUsage(1, 1))
    llm = FakeLlmAdapter(structured=[result, LlmUnavailableError("caído")])
    messages = [LlmMessage(LlmRole.USER, "hola")]
    request = RequestId("req_0001")
    assert (
        run(
            llm.complete_structured(
                messages=messages, tools=None, response_schema=None, request_id=request
            )
        )
        == result
    )
    with pytest.raises(LlmUnavailableError, match="caído"):
        run(
            llm.complete_structured(
                messages=messages, tools=None, response_schema=None, request_id=request
            )
        )
    with pytest.raises(LlmUnavailableError, match="guion"):
        run(
            llm.complete_structured(
                messages=messages, tools=None, response_schema=None, request_id=request
            )
        )
    assert llm.pending == 0
    assert len(llm.calls) == 3


def test_llm_rejects_unstructured_answer_to_a_schema_request() -> None:
    llm = FakeLlmAdapter(structured=[LlmStructuredResult("texto", (), TokenUsage())])
    with pytest.raises(LlmMalformedOutputError):
        run(
            llm.complete_structured(
                messages=[LlmMessage(LlmRole.USER, "plan")],
                tools=None,
                response_schema={"type": "object"},
                request_id=RequestId("req_0002"),
            )
        )


def test_llm_stream_ends_with_tokens_and_fails_without_script() -> None:
    async def chunks(llm: FakeLlmAdapter) -> list[object]:
        messages = [LlmMessage(LlmRole.USER, "hola")]
        return [
            c async for c in llm.stream_text(messages=messages, request_id=RequestId("req_0001"))
        ]

    out = run(chunks(FakeLlmAdapter(streams=[("a", "b")])))
    assert [getattr(c, "final", None) for c in out] == [False, True]
    with pytest.raises(LlmUnavailableError):
        run(chunks(FakeLlmAdapter()))
    with pytest.raises(LlmUnavailableError, match="caído"):
        run(chunks(FakeLlmAdapter(streams=[LlmUnavailableError("caído")])))


def test_embedding_fixed_vectors_and_dimension_checks() -> None:
    adapter = FakeEmbeddingAdapter(dimension=3, fixed={"a": (1.0, 0.0, 0.0)})
    assert run(adapter.embed(["a"])) == [(1.0, 0.0, 0.0)]
    with pytest.raises(EmbeddingDimensionMismatchError):
        run(FakeEmbeddingAdapter(dimension=3, fixed={"a": (1.0,)}).embed(["a"]))
    with pytest.raises(LlmUnavailableError):
        run(FakeEmbeddingAdapter(fail_with=LlmUnavailableError()).embed(["a"]))
    with pytest.raises(EmbeddingDimensionMismatchError):
        cosine((1.0,), (1.0, 0.0))
    assert cosine((0.0, 0.0), (1.0, 0.0)) == 0.0


def test_event_sink_never_raises_even_when_broken() -> None:
    event = DomainEvent(CORRELATION, 1, at(), ModePayload(ResponseMode.SUPERVISOR_DIRECT))
    broken = ListEventSink(broken=True)
    run(broken.emit(event))
    assert (broken.events, broken.dropped) == ([], [event])


# --- Repositorios: las garantías de 7.4 ---


def test_conversation_message_and_calls_are_saved_together_or_not_at_all() -> None:
    repo = InMemoryConversationRepository()
    run(repo.create(NewConversation(CONVERSATION, PRINCIPAL, Locale.ES, at())))
    message = NewMessage(
        MessageId("msg_0002"),
        CONVERSATION,
        MessageRole.ASSISTANT,
        "Hay 4 monitores en KO.",
        TurnStatus.COMPLETED,
        CORRELATION,
        at(2),
    )
    foreign = NewToolCall(
        CallId("cal_1"),
        MessageId("msg_9999"),
        StepId("s1"),
        VIGIA_SYSTEM,
        "query_metric",
        {},
        ok=True,
        created_at=at(1),
    )
    with pytest.raises(ValidationError):
        run(repo.append_message(message, [foreign]))
    empty = run(repo.get_thread(CONVERSATION, requester()))
    assert empty is not None
    assert empty.messages == ()
    run(repo.append_message(message, [replace(foreign, message_id=message.message_id)]))
    thread = run(repo.get_thread(CONVERSATION, requester()))
    assert thread is not None
    assert [m.content for m in thread.messages] == ["Hay 4 monitores en KO."]
    with pytest.raises(ValidationError):
        run(repo.append_message(message, []))


def test_someone_elses_thread_looks_like_a_missing_one() -> None:
    repo = InMemoryConversationRepository()
    run(repo.create(NewConversation(CONVERSATION, PRINCIPAL, Locale.ES, at())))
    assert run(repo.get_thread(CONVERSATION, requester(OTHER, Role.ADMIN))) is None
    assert run(repo.get_thread(CONVERSATION.__class__("cnv_9999"), requester())) is None
    with pytest.raises(ValidationError):
        run(repo.create(NewConversation(CONVERSATION, PRINCIPAL, Locale.ES, at())))


def test_feedback_is_idempotent_per_message_and_person() -> None:
    repo = InMemoryConversationRepository()
    vote = Feedback(MessageId("msg_0002"), PRINCIPAL, Rating.UP, at())
    assert run(repo.record_feedback(vote)) is FeedbackOutcome.CREATED
    assert run(repo.record_feedback(replace(vote, at=at(9)))) is FeedbackOutcome.UNCHANGED
    assert run(repo.record_feedback(replace(vote, rating=Rating.DOWN))) is FeedbackOutcome.UPDATED
    assert len(repo.feedback) == 1


def test_touch_only_moves_forward() -> None:
    repo = InMemoryConversationRepository()
    run(repo.create(NewConversation(CONVERSATION, PRINCIPAL, Locale.ES, at(5))))
    run(repo.touch(CONVERSATION, at(1)))
    assert repo.updated_at[CONVERSATION] == at(5)
    run(repo.touch(CONVERSATION, at(9)))
    assert repo.updated_at[CONVERSATION] == at(9)


def test_a_turn_is_written_once() -> None:
    repo = InMemoryTurnRepository()
    run(repo.save(direct_turn()))
    with pytest.raises(ValidationError):
        run(repo.save(direct_turn()))
    assert run(repo.get(TURN)) == direct_turn()


def test_memory_upsert_increments_hits_atomically_and_filters_by_similarity() -> None:
    repo = InMemoryMemoryRepository()
    vector = deterministic_vector("monitores en KO")
    draft = MemoryExampleDraft(
        "monitores en ko", "¿Monitores en KO?", vector, query_plan(), Locale.ES
    )
    first = run(repo.upsert_example(draft))
    assert run(repo.upsert_example(draft)) == first
    found = run(repo.similar_plans(vector, k=3, min_sim=0.99))
    assert [(e.memory_id, e.hits) for e in found] == [(first, 2)]
    assert run(repo.similar_plans(deterministic_vector("margen"), k=3, min_sim=0.9)) == []
    run(repo.deactivate(first, PRINCIPAL))
    assert run(repo.similar_plans(vector, k=3, min_sim=0.0)) == []
    with pytest.raises(ValidationError):
        run(repo.deactivate(first.__class__("mem_9999"), PRINCIPAL))


def test_gap_record_creates_or_increments_without_race() -> None:
    repo = InMemoryGapRepository()

    def draft(question: str, seconds: float) -> GapDraft:
        return GapDraft(
            question.lower(),
            question,
            deterministic_vector(question),
            Locale.ES,
            "no_coverage",
            at(seconds),
        )

    first = run(repo.record(draft("Contratos de Getafe", 1)))
    assert run(repo.record(draft("Contratos de Getafe", 5))) == first
    run(repo.record(draft("Clima en Bilbao", 2)))
    clusters = run(repo.list_clusters(GapFilter()))
    assert [(c.questions, c.occurrences) for c in clusters] == [
        (("Contratos de Getafe",), 2),
        (("Clima en Bilbao",), 1),
    ]
    assert clusters[0].last_seen == at(5)
    assert len(run(repo.list_clusters(GapFilter(min_occurrences=2)))) == 1
    assert run(repo.list_clusters(GapFilter(locale=Locale.EN))) == []
    with pytest.raises(ValidationError):
        GapFilter(limit=0)


def test_knowledge_below_threshold_returns_nothing_never_the_closest() -> None:
    chunk = StoredChunk("manual.pdf", 0, "Manual", "Reiniciar el monitor", (1.0, 0.0))
    repo = InMemoryKnowledgeRepository([chunk])
    assert [c.source for c in run(repo.search((1.0, 0.0), k=1, min_sim=0.8))] == ["manual.pdf"]
    assert run(repo.search((0.0, 1.0), k=1, min_sim=0.8)) == []


def test_brief_keeps_one_row_with_its_age() -> None:
    repo = InMemoryBriefRepository()
    assert run(repo.get()) is None
    brief = SituationBrief(at(), (evidence_fact(),))
    run(repo.put(brief))
    assert run(repo.get()) == brief
    assert brief.age_seconds(at(240)) == 240
    assert brief.age_seconds(at(-5)) == 0


def test_glossary_records_history_in_the_same_change() -> None:
    repo = InMemoryGlossaryRepository()
    term = GlossaryTerm("monitor en ko", "Monitor en KO", "Monitor sin señal")
    assert run(repo.upsert(term, PRINCIPAL, at())).action is GlossaryAction.CREATE
    updated = replace(term, definition="Monitor que no reporta")
    assert run(repo.upsert(updated, PRINCIPAL, at(1))).before == term
    run(repo.deactivate(term.term, PRINCIPAL, at(2)))
    assert run(repo.list_active()) == ()
    assert run(repo.get(term.term)) == replace(updated, active=False)
    assert [c.action for c in run(repo.history(term.term))] == [
        GlossaryAction.CREATE,
        GlossaryAction.UPDATE,
        GlossaryAction.DEACTIVATE,
    ]
    with pytest.raises(ValidationError):
        run(repo.deactivate(term.term, PRINCIPAL, at(3)))


def test_topics_by_demand_and_status() -> None:
    repo = InMemoryTopicRepository()

    def topic(n: int, asked: int) -> Topic:
        return Topic(
            TopicId(f"top_000{n}"),
            f"tema {n}",
            asked,
            0,
            asked,
            frozenset(),
            TopicStatus.OBSERVANDO,
            at(),
            at(),
        )

    run(repo.upsert(topic(1, 3)))
    run(repo.upsert(topic(2, 9)))
    assert [t.asked for t in run(repo.list_by_demand(5))] == [9, 3]
    changed = run(repo.set_status(TopicId("top_0001"), TopicStatus.PLANIFICADO, at(1)))
    assert changed.status is TopicStatus.PLANIFICADO
    with pytest.raises(ValidationError):
        run(repo.set_status(TopicId("top_9999"), TopicStatus.CUBIERTO, at(1)))


def _approval(expires: float = 600) -> HumanApprovalRequest:
    return HumanApprovalRequest(
        ApprovalId("apr_0001"),
        TURN,
        VIGIA,
        "export",
        Impact.HIGH,
        "exportar el informe",
        (),
        Role.MANAGER,
        at(expires),
    )


def test_approval_decides_only_once_and_only_in_time() -> None:
    repo = InMemoryApprovalRepository()
    assert run(repo.create(_approval())).status is ApprovalStatus.PENDING
    with pytest.raises(ValidationError):
        run(repo.create(_approval()))
    with pytest.raises(InvalidTransitionError):
        run(repo.decide(ApprovalId("apr_0001"), ApprovalStatus.EXPIRED, OTHER, at(1)))
    decided = run(repo.decide(ApprovalId("apr_0001"), ApprovalStatus.APPROVED, OTHER, at(1)))
    assert (decided.decided_by, decided.approved) == (OTHER, True)
    with pytest.raises(InvalidTransitionError):
        run(repo.decide(ApprovalId("apr_0001"), ApprovalStatus.REJECTED, OTHER, at(2)))
    with pytest.raises(ValidationError):
        run(repo.decide(ApprovalId("apr_9999"), ApprovalStatus.APPROVED, OTHER, at(2)))


def test_pending_approvals_expire_together() -> None:
    repo = InMemoryApprovalRepository()
    run(repo.create(_approval(expires=60)))
    assert run(repo.expire_due(at(30))) == ()
    with pytest.raises(InvalidTransitionError):
        run(repo.decide(ApprovalId("apr_0001"), ApprovalStatus.APPROVED, OTHER, at(60)))
    assert run(repo.expire_due(at(60))) == (ApprovalId("apr_0001"),)
    expired = run(repo.get(ApprovalId("apr_0001")))
    assert expired is not None
    assert expired.status is ApprovalStatus.EXPIRED


def test_lifecycle_only_follows_the_four_transitions() -> None:
    repo = InMemoryAgentLifecycleRepository()
    discovered = AgentLifecycleEntry(VIGIA, AgentLifecycleState.DISCOVERED, "1.0.0", at())
    run(repo.register(discovered, PRINCIPAL))
    with pytest.raises(ValidationError):
        run(repo.register(discovered, PRINCIPAL))
    jump = replace(
        discovered,
        state=AgentLifecycleState.CERTIFIED,
        owner="equipo red",
        certified_at=at(1),
        report_ref="cert-001",
        updated_at=at(1),
    )
    with pytest.raises(InvalidTransitionError):
        run(repo.transition(jump, "salto", PRINCIPAL))
    run(repo.transition(replace(discovered, state=AgentLifecycleState.COMPATIBLE), "ok", PRINCIPAL))
    run(repo.transition(jump, "golden set superado", PRINCIPAL))
    assert run(repo.get(VIGIA)) == jump
    assert [c.to_state for c in run(repo.history(VIGIA))] == [
        AgentLifecycleState.CERTIFIED,
        AgentLifecycleState.COMPATIBLE,
        AgentLifecycleState.DISCOVERED,
    ]
    with pytest.raises(InvalidTransitionError):
        run(repo.register(replace(jump, agent_id=PLENDATA), PRINCIPAL))
    with pytest.raises(ValidationError):
        run(repo.transition(replace(discovered, agent_id=PLENDATA), "x", PRINCIPAL))
