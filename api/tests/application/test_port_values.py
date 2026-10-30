"""Prompt 5: los valores que cruzan los puertos se validan al construirse."""

import asyncio
from dataclasses import replace
from decimal import Decimal

import pytest

from carmen.application.events import (
    AgentResultPayload,
    ApprovalRequiredPayload,
    DomainEvent,
    DonePayload,
    ErrorPayload,
    GroundingPayload,
    ModePayload,
    StagePayload,
    ToolResultPayload,
    WarningPayload,
)
from carmen.application.ports.egress import EgressOutcome, Url
from carmen.application.ports.identity import Audience
from carmen.application.ports.llm import (
    LlmDescriptor,
    LlmMessage,
    LlmRole,
    LlmStructuredResult,
    LlmTextChunk,
    LlmToolCall,
    ToolSpec,
)
from carmen.application.ports.mcp import (
    MAX_ROWS,
    EnvelopeFact,
    EnvelopeWarning,
    HealthStatus,
    SystemHealth,
    ToolDescriptor,
    ToolInvocation,
)
from carmen.application.ports.model_provider import ModelPayload
from carmen.application.ports.repositories import (
    AgentLifecycleEntry,
    GlossaryTerm,
    NewToolCall,
    Topic,
    TopicId,
    TopicStatus,
)
from carmen.domain.agents.card import AgentLifecycleState
from carmen.domain.approval.models import Impact
from carmen.domain.conversation.turn import TokenUsage, TurnStatus
from carmen.domain.delegation.models import AgentResultStatus
from carmen.domain.egress.models import Purpose
from carmen.domain.errors import ValidationError
from carmen.domain.ids import ApprovalId, CallId, MessageId, Scope, StepId, TaskId
from carmen.domain.orchestration.mode import ResponseMode
from support.builders import (
    CALL,
    CONVERSATION,
    CORRELATION,
    MESSAGE,
    VIGIA,
    VIGIA_SYSTEM,
    at,
    delegation_plan,
    envelope,
    execution_context,
    requester,
)
from support.fakes import FakeTokenExchange, FrozenClock

pytestmark = pytest.mark.application


def test_message_id_follows_its_pattern() -> None:
    assert MessageId("msg_0001") == MESSAGE
    with pytest.raises(ValidationError):
        MessageId("mensaje_1")


# --- Contexto ---


def test_context_deadline_comes_after_the_start_and_expires() -> None:
    ctx = execution_context(deadline_seconds=30)
    assert not ctx.expired(at(29))
    assert ctx.expired(at(30))
    assert not execution_context(deadline_seconds=None).expired(at(10_000))
    with pytest.raises(ValidationError, match="posterior"):
        execution_context(deadline_seconds=0)


def test_context_freezes_catalog_versions_and_hides_the_token() -> None:
    ctx = execution_context()
    with pytest.raises(TypeError):
        ctx.catalog_versions[VIGIA_SYSTEM] = "otra"  # type: ignore[index]
    assert "user-token-fixture" not in repr(ctx)
    assert str(ctx.requester.token) == "UserToken(***)"


# --- Eventos ---


def test_events_reject_negative_counters_and_empty_text() -> None:
    with pytest.raises(ValidationError):
        StagePayload(" ")
    with pytest.raises(ValidationError):
        ToolResultPayload(VIGIA, TaskId("t1"), StepId("s1"), CALL, True, -1, 0, False)
    with pytest.raises(ValidationError):
        AgentResultPayload(TaskId("t1"), VIGIA, AgentResultStatus.OK, 0, -5)
    with pytest.raises(ValidationError):
        ApprovalRequiredPayload(ApprovalId("apr_0001"), VIGIA, "", Impact.HIGH, at(60))
    with pytest.raises(ValidationError):
        GroundingPayload(ok=True, checked=-1, unsupported=())
    with pytest.raises(ValidationError):
        WarningPayload("", "falta un sistema")
    with pytest.raises(ValidationError):
        ErrorPayload("internal", " ", recoverable=False)


def _done(mode: ResponseMode, plan: bool) -> DonePayload:
    return DonePayload(
        message_id=MESSAGE,
        conversation_id=CONVERSATION,
        status=TurnStatus.COMPLETED,
        partial=False,
        missing_systems=(),
        grounding_ok=None,
        plan_id=delegation_plan().plan_id if plan else None,
        round=1,
        repairs=0,
        latency_ms=10,
        model="fake-model",
        catalog_versions={VIGIA_SYSTEM: "2026-07-20"},
        response_mode=mode,
        agents_used=(),
        missing_agents=(),
    )


def test_done_carries_a_plan_if_and_only_if_the_turn_delegated() -> None:
    assert _done(ResponseMode.DELEGATE_SINGLE, plan=True).plan_id is not None
    assert _done(ResponseMode.SUPERVISOR_DIRECT, plan=False).plan_id is None
    with pytest.raises(ValidationError, match="plan_id"):
        _done(ResponseMode.DELEGATE_MULTI, plan=False)
    with pytest.raises(ValidationError, match="plan_id"):
        _done(ResponseMode.SUPERVISOR_DIRECT, plan=True)


def test_domain_event_sequence_starts_at_one() -> None:
    payload = ModePayload(ResponseMode.SUPERVISOR_DIRECT)
    assert DomainEvent(CORRELATION, 1, at(), payload).event_type.value == "mode"
    for bad in (0, True):
        with pytest.raises(ValidationError, match="sequence"):
            DomainEvent(CORRELATION, bad, at(), payload)


# --- LLM ---


def test_llm_messages_and_tools() -> None:
    assert LlmMessage(LlmRole.TOOL, "{}", tool_call_id="c1").tool_call_id == "c1"
    with pytest.raises(ValidationError, match="tool_call_id"):
        LlmMessage(LlmRole.TOOL, "{}")
    with pytest.raises(ValidationError, match="tool_call_id"):
        LlmMessage(LlmRole.USER, "hola", tool_call_id="c1")
    with pytest.raises(ValidationError, match="herramienta"):
        ToolSpec("Query-Metric", "consulta", {})
    call = LlmToolCall("c1", "query_metric", {"periodo": "mes_actual"})
    with pytest.raises(TypeError):
        call.arguments["periodo"] = "otro"  # type: ignore[index]


def test_llm_results_chunks_and_descriptor() -> None:
    tokens = TokenUsage(tokens_in=1, tokens_out=1)
    with pytest.raises(ValidationError, match="texto, llamadas"):
        LlmStructuredResult(None, (), tokens)
    assert LlmStructuredResult(None, (), tokens, structured={"ok": True}).structured
    with pytest.raises(ValidationError, match="index"):
        LlmTextChunk(-1, "a")
    with pytest.raises(ValidationError, match="último"):
        LlmTextChunk(0, "a", tokens=tokens)
    descriptor = LlmDescriptor("fake", "fake-model", "r1", Decimal("0.2"), "cfg")
    for bad in (Decimal("2.1"), Decimal("-0.1"), Decimal("NaN")):
        with pytest.raises(ValidationError, match="temperatura"):
            replace(descriptor, temperature=bad)


# --- MCP ---


def test_envelope_rules() -> None:
    warning = EnvelopeWarning("partial_data", "faltan estaciones")
    assert envelope(partial=False).facts
    with pytest.raises(ValidationError, match="parcial"):
        replace(envelope(), partial=True)
    assert replace(envelope(), partial=True, warnings=(warning,)).partial
    with pytest.raises(ValidationError, match="versión"):
        replace(envelope(), schema_version="2.0")
    with pytest.raises(ValidationError, match="filas"):
        replace(envelope(), rows=tuple({"n": i} for i in range(MAX_ROWS + 1)))
    fact = EnvelopeFact(key="monitores_ko", label="Monitores en KO", value=4)
    with pytest.raises(ValidationError, match="repite"):
        envelope(fact, fact)
    rows = replace(envelope(), rows=({"n": 1},)).rows
    with pytest.raises(TypeError):
        rows[0]["n"] = 2  # type: ignore[index]
    with pytest.raises(ValidationError):
        EnvelopeWarning("", "x")


def test_tool_descriptor_invocation_and_health() -> None:
    with pytest.raises(ValidationError, match="herramienta"):
        ToolDescriptor(VIGIA_SYSTEM, "1tool", "consulta", {}, "2026-07-20")
    exchange = FakeTokenExchange(clock=FrozenClock())
    token = asyncio.run(
        exchange.exchange(
            user_token=requester().token,
            audience=Audience("api://vigia"),
            scopes=frozenset({Scope("vigia.read")}),
        )
    )
    with pytest.raises(ValidationError, match="herramienta"):
        ToolInvocation(CallId("cal_0001"), StepId("s1"), VIGIA_SYSTEM, "Bad", {}, token)
    assert SystemHealth(VIGIA_SYSTEM, HealthStatus.UP, at(), latency_ms=0).latency_ms == 0
    with pytest.raises(ValidationError):
        SystemHealth(VIGIA_SYSTEM, HealthStatus.DOWN, at(), latency_ms=-1)


# --- Salida y proveedores ---


def test_egress_outcome_revalidates_the_final_domain_and_cost() -> None:
    url = Url("https://www.boe.es/diario")
    outcome = EgressOutcome(url, "www.boe.es", at(), "texto", (), Decimal(0), "egr_boe")
    assert outcome.domain == url.domain
    with pytest.raises(ValidationError, match="dominio"):
        replace(outcome, domain="boe.es")
    for cost in (Decimal(-1), Decimal("NaN")):
        with pytest.raises(ValidationError, match="cost_eur"):
            replace(outcome, cost_eur=cost)


def test_model_payload_needs_a_message_and_tokens() -> None:
    message = (LlmMessage(LlmRole.USER, "resume"),)
    assert ModelPayload("m", Purpose.NARRATION, message, 1).max_tokens == 1
    with pytest.raises(ValidationError, match="mensaje"):
        ModelPayload("m", Purpose.NARRATION, (), 10)
    for bad in (0, True):
        with pytest.raises(ValidationError, match="max_tokens"):
            ModelPayload("m", Purpose.NARRATION, message, bad)


# --- Registros de los repositorios ---


def test_repository_records_validate_themselves() -> None:
    with pytest.raises(ValidationError, match="error_code"):
        NewToolCall(CALL, MESSAGE, StepId("s1"), VIGIA_SYSTEM, "query_metric", {}, False, at())
    with pytest.raises(ValidationError, match="normalizada"):
        GlossaryTerm("Estación KO", "Estación KO", "Una estación sin servicio")
    with pytest.raises(ValidationError, match="superar"):
        Topic(
            TopicId("top_0001"),
            "alarmas",
            asked=1,
            resolved=1,
            unresolved=1,
            systems=frozenset({VIGIA_SYSTEM}),
            status=TopicStatus.OBSERVANDO,
            first_seen=at(),
            last_seen=at(1),
        )
    with pytest.raises(ValidationError, match="CERTIFIED"):
        AgentLifecycleEntry(VIGIA, AgentLifecycleState.CERTIFIED, "1.0.0", at(), owner="ops")
    certified = AgentLifecycleEntry(
        VIGIA,
        AgentLifecycleState.CERTIFIED,
        "1.0.0",
        at(),
        owner="ops",
        certified_at=at(),
        report_ref="cert-001",
    )
    assert certified.state is AgentLifecycleState.CERTIFIED
