"""Prompt 8: el turno, sus ejecuciones, aprobaciones y ciclo de vida (7.3.1, 7.4, 7.11.2)."""

from dataclasses import replace
from decimal import Decimal

import asyncpg
import pytest
from sqlalchemy.exc import IntegrityError

from carmen.adapters.persistence.approvals.repository import PgApprovalRepository
from carmen.adapters.persistence.conversation.repository import PgConversationRepository
from carmen.adapters.persistence.conversation.turns import PgTurnRepository
from carmen.adapters.persistence.engine import Database
from carmen.adapters.persistence.lifecycle.repository import PgAgentLifecycleRepository
from carmen.application.ports.repositories import (
    AgentLifecycleEntry,
    MessageRole,
    NewConversation,
    NewMessage,
    NewToolCall,
)
from carmen.domain.agents.card import AgentLifecycleState
from carmen.domain.approval.models import (
    ApprovalRecord,
    ApprovalStatus,
    HumanApprovalRequest,
    Impact,
)
from carmen.domain.conversation.turn import ConversationTurn, TokenUsage, TurnStatus
from carmen.domain.delegation.models import (
    AgentResult,
    AgentResultStatus,
    ExternalCallTrace,
    ToolCallTrace,
)
from carmen.domain.errors import InvalidTransitionError, ValidationError
from carmen.domain.evidence.grounding import GroundingClaim, GroundingResult, TextSpan
from carmen.domain.evidence.models import (
    EntityRef,
    EvidenceMedia,
    EvidencePassage,
    EvidenceReference,
    PeriodInterpreted,
)
from carmen.domain.ids import (
    AgentId,
    ApprovalId,
    CallId,
    ClaimId,
    MediaId,
    MessageId,
    PassageId,
    PrincipalId,
    ProviderId,
    RunId,
    Scope,
    StepId,
    TurnId,
)
from carmen.domain.locale import Locale
from carmen.domain.orchestration.mode import ResponseMode
from carmen.domain.policy.models import AgentAction, Effect, PolicyDecision
from carmen.domain.role import Role
from carmen.domain.system import SystemId
from repositories.pg import Pg
from support.builders import (
    CONVERSATION,
    CORRELATION,
    PLENDATA,
    PLENDATA_SYSTEM,
    POLICY_VERSION,
    PRINCIPAL,
    TURN,
    VIGIA,
    VIGIA_SYSTEM,
    agent_result,
    agent_task,
    at,
    delegated_turn,
    delegation_plan,
    direct_turn,
    evidence_fact,
)
from support.fakes.system import FrozenClock

pytestmark = pytest.mark.repositories

QUESTION = "¿Cuántos monitores hay en KO y cuánto se ha facturado?"
USER_MSG = MessageId("msg_0001")
ANSWER = MessageId("msg_0002")
VIGIA_CALL = CallId("cal_vigia1")
PLENDATA_CALL = CallId("cal_plendata1")
MANAGER = PrincipalId("usr_m4n4")


# --- Constructores del escenario ---------------------------------------------------------


def message(mid: MessageId, role: MessageRole, content: str, status: TurnStatus) -> NewMessage:
    return NewMessage(
        mid, CONVERSATION, role, content, status, CORRELATION, at(1 if mid == USER_MSG else 5)
    )


def call(call_id: CallId, system: SystemId, *, ok: bool = True) -> NewToolCall:
    return NewToolCall(
        call_id=call_id,
        message_id=ANSWER,
        step_id=StepId("s1"),
        system_id=system,
        tool_name="query_metric",
        arguments={"metric": "monitores_ko"},
        ok=ok,
        created_at=at(3),
        error_code=None if ok else "timeout",
        ms=120,
    )


def trace(c: NewToolCall) -> ToolCallTrace:
    return ToolCallTrace(c.call_id, c.system_id, c.tool_name, c.ms or 0, c.ok)


def decision(agent: AgentId, effect: Effect = Effect.ALLOW) -> PolicyDecision:
    return PolicyDecision(
        turn_id=TURN,
        principal_id=PRINCIPAL,
        action=AgentAction.INVOKE,
        decision=effect,
        reason_code="grant" if effect is Effect.ALLOW else "explicit_deny",
        policy_version=POLICY_VERSION,
        decided_at=at(2),
        agent_id=agent,
        scopes=frozenset({Scope("vigia.read.limited")}) if effect is Effect.ALLOW else frozenset(),
    )


def two_agent_turn() -> tuple[ConversationTurn, list[AgentResult], list[NewToolCall]]:
    """VigIA devuelve un hecho y un pasaje; Plendata, un hecho y un adjunto, con anclaje."""
    vigia_task = agent_task(1, VIGIA)
    plendata_task = agent_task(2, PLENDATA, objective="facturación del mes en curso")
    plan = delegation_plan(vigia_task, plendata_task)
    calls = [call(VIGIA_CALL, VIGIA_SYSTEM), call(PLENDATA_CALL, PLENDATA_SYSTEM)]
    ko = replace(
        evidence_fact("monitores_ko", 4, call_id=VIGIA_CALL),
        entity=EntityRef("estacion", "alc-01", "Alcorcón"),
        dimensions={"region": "centro"},
        period=PeriodInterpreted("this_month", at(-86400), at(0), "este mes"),
    )
    passage = EvidencePassage(
        passage_id=PassageId("psg_runbook1"),
        call_id=VIGIA_CALL,
        system_id=VIGIA_SYSTEM,
        document_id="runbook-ko",
        title="Qué hacer con un monitor en KO",
        text="Revisar la alimentación del equipo.",
        kind="procedure",
        relevance=0.82,
        section="2.1",
        updated_at=at(-3600),
    )
    billed = evidence_fact(
        "facturado", Decimal("1520.40"), call_id=PLENDATA_CALL, system=PLENDATA_SYSTEM
    )
    chart = EvidenceMedia(
        media_id=MediaId("med_chart1"),
        call_id=PLENDATA_CALL,
        system_id=PLENDATA_SYSTEM,
        document_id="informe-mes",
        mime="image/png",
        caption="Facturación diaria",
        uri="https://plendata.example/informe-mes/chart.png",
        bytes=2048,
    )
    vigia = replace(
        agent_result(vigia_task, evidence=(ko, passage)),
        run=replace(
            agent_result(vigia_task).run,
            run_id=RunId("run_t1vigia"),
            tokens_in=300,
            tokens_out=40,
            cost_eur=Decimal("0.0125"),
            tool_calls=(trace(calls[0]),),
            policy_checks=(decision(VIGIA),),
        ),
    )
    plendata = replace(
        agent_result(plendata_task, evidence=(billed, chart)),
        run=replace(
            agent_result(plendata_task).run,
            run_id=RunId("run_t2plendata"),
            tool_calls=(trace(calls[1]),),
            external=(
                ExternalCallTrace(
                    "egress-v1", at(3), provider=ProviderId("provider.mistral"), tokens=10
                ),
            ),
        ),
    )
    results = [vigia, plendata]
    claims = (
        GroundingClaim(
            ClaimId("clm_1"),
            TextSpan(10, 11),
            "4",
            Decimal(4),
            EvidenceReference.to(ko),
            "supported",
        ),
        GroundingClaim(
            ClaimId("clm_2"), TextSpan(20, 24), "2025", None, None, "whitelisted", "año"
        ),
    )
    turn = replace(
        delegated_turn(plan, results, question=QUESTION, latency_ms=2300),
        grounding=GroundingResult.of(claims),
    )
    return turn, results, calls


async def store_messages(
    db: Database, turn: ConversationTurn, calls: list[NewToolCall], *, status: TurnStatus
) -> None:
    conversations = PgConversationRepository()
    await conversations.create(NewConversation(CONVERSATION, PRINCIPAL, Locale.ES, at(0)))
    await conversations.append_message(
        message(USER_MSG, MessageRole.USER, turn.question, status), []
    )
    await conversations.append_message(
        message(ANSWER, MessageRole.ASSISTANT, "Hay 4 monitores en KO.", status), calls
    )


async def answer_turn(
    db: Database,
    turn: ConversationTurn,
    results: list[AgentResult],
    calls: list[NewToolCall],
) -> None:
    """Unidad de trabajo 1: mensajes, llamadas, turno, ejecuciones y evidencia, o nada."""
    async with db.unit_of_work():
        await store_messages(db, turn, calls, status=turn.status)
        await PgTurnRepository().save(turn, message_id=ANSWER, results=results)


# --- Turno -------------------------------------------------------------------------------


def test_a_direct_turn_is_stored_without_runs_and_at_zero_cost(pg: Pg) -> None:
    turn = direct_turn(QUESTION)

    async def scenario(db: Database) -> ConversationTurn | None:
        await answer_turn(db, turn, [], [])
        async with db.unit_of_work():
            return await PgTurnRepository().get(TURN)

    assert pg.run(scenario) == turn
    assert pg.fetch("SELECT id FROM carmen.agent_runs") == []
    row = pg.fetch(
        "SELECT turn_id, response_mode::text, cost_eur, agents_used, delegation_plan"
        " FROM carmen.messages WHERE id = $1",
        str(ANSWER),
    )[0]
    assert (row["turn_id"], row["response_mode"]) == (str(TURN), "SUPERVISOR_DIRECT")
    assert row["cost_eur"] == Decimal(0)
    assert (row["agents_used"], row["delegation_plan"]) == ([], None)


def test_a_two_agent_turn_is_stored_whole_and_reconstructed_equal(pg: Pg) -> None:
    turn, results, calls = two_agent_turn()

    async def scenario(db: Database) -> ConversationTurn | None:
        await answer_turn(db, turn, results, calls)
        async with db.unit_of_work():
            return await PgTurnRepository().get(TURN)

    assert pg.run(scenario) == turn
    runs = pg.fetch(
        "SELECT r.id, r.task_id, r.agent_id, r.agent_version, r.status::text, r.cost_eur,"
        " array_agg(t.call_id ORDER BY t.run_ord) AS calls"
        " FROM carmen.agent_runs r JOIN carmen.tool_calls t ON t.agent_run_id = r.id"
        " WHERE r.message_id = $1 GROUP BY r.id ORDER BY r.ord",
        str(ANSWER),
    )
    assert [(r["id"], r["task_id"], r["agent_id"], r["status"], r["calls"]) for r in runs] == [
        ("run_t1vigia", "t1", "agent.vigia", "ok", ["cal_vigia1"]),
        ("run_t2plendata", "t2", "agent.plendata", "ok", ["cal_plendata1"]),
    ]
    assert runs[0]["cost_eur"] == Decimal("0.0125")
    counts = pg.fetch(
        "SELECT (SELECT count(*) FROM carmen.evidence_facts) AS facts,"
        " (SELECT count(*) FROM carmen.evidence_passages) AS passages,"
        " (SELECT count(*) FROM carmen.evidence_media) AS media,"
        " (SELECT count(*) FROM carmen.grounding_claims) AS claims,"
        " (SELECT count(*) FROM carmen.policy_decisions) AS decisions,"
        " (SELECT count(*) FROM carmen.external_calls) AS external"
    )[0]
    assert dict(counts) == {
        "facts": 2,
        "passages": 1,
        "media": 1,
        "claims": 2,
        "decisions": 1,
        "external": 1,
    }


def test_the_turn_answers_who_which_mode_agents_tools_and_cost(pg: Pg) -> None:
    """Resultado verificable del Prompt 8: el turno se reconstruye desde SQL, sin el dominio."""
    turn, results, calls = two_agent_turn()
    pg.run(lambda db: answer_turn(db, turn, results, calls))
    row = pg.fetch(
        "SELECT c.user_id, m.response_mode::text AS mode, m.agents_used, m.cost_eur,"
        " (SELECT array_agg(DISTINCT t.tool_name) FROM carmen.tool_calls t"
        "  WHERE t.message_id = m.id) AS tools"
        " FROM carmen.messages m JOIN carmen.conversations c ON c.id = m.conversation_id"
        " WHERE m.turn_id = $1",
        str(TURN),
    )[0]
    assert dict(row) == {
        "user_id": str(PRINCIPAL),
        "mode": "DELEGATE_MULTI",
        "agents_used": ["agent.plendata", "agent.vigia"],
        "cost_eur": Decimal("0.0125"),
        "tools": ["query_metric"],
    }


def test_a_failure_writing_evidence_rolls_back_the_whole_turn(pg: Pg) -> None:
    turn, results, calls = two_agent_turn()
    stray = evidence_fact("monitores_ko", 9, call_id=VIGIA_CALL)  # misma clave: uq_fact
    broken = replace(turn, evidence=(*turn.evidence, stray), grounding=None)

    async def scenario(db: Database) -> None:
        with pytest.raises(IntegrityError, match="uq_fact"):
            await answer_turn(db, broken, results, calls)

    pg.run(scenario)
    for table in ("messages", "tool_calls", "agent_runs", "evidence_facts", "conversations"):
        assert pg.fetch(f"SELECT 1 FROM carmen.{table}") == [], table


def test_evidence_from_a_call_that_is_not_in_the_message_is_refused(pg: Pg) -> None:
    turn, results, calls = two_agent_turn()
    foreign = evidence_fact("otra", 1, call_id=CallId("cal_ajena"))
    broken = replace(turn, evidence=(*turn.evidence, foreign))

    async def scenario(db: Database) -> None:
        with pytest.raises(ValidationError, match="cal_ajena"):
            await answer_turn(db, broken, results, calls)

    pg.run(scenario)
    assert pg.fetch("SELECT 1 FROM carmen.messages") == []


def test_a_turn_is_never_rewritten_and_must_match_its_messages(pg: Pg) -> None:
    turn, results, calls = two_agent_turn()
    repo = PgTurnRepository()

    async def scenario(db: Database) -> None:
        await answer_turn(db, turn, results, calls)
        with pytest.raises(ValidationError, match="no se reescribe"):
            async with db.unit_of_work():
                await repo.save(turn, message_id=ANSWER, results=results)
        with pytest.raises(ValidationError, match="ejecuciones"):
            async with db.unit_of_work():
                await repo.save(turn, message_id=ANSWER, results=results[:1])
        with pytest.raises(ValidationError, match="no existe"):
            async with db.unit_of_work():
                await repo.save(direct_turn(QUESTION), message_id=MessageId("msg_9999"))
        with pytest.raises(ValidationError, match="pregunta"):
            async with db.unit_of_work():
                await repo.save(
                    direct_turn("otra pregunta", turn_id=TurnId("trn_otro2")),
                    message_id=ANSWER,
                )
        async with db.unit_of_work():
            assert await repo.get(TurnId("trn_nada")) is None

    pg.run(scenario)


def test_a_trace_must_match_the_stored_tool_call(pg: Pg) -> None:
    turn, results, calls = two_agent_turn()
    lying = replace(
        results[0],
        run=replace(results[0].run, tool_calls=(replace(trace(calls[0]), ok=False),)),
    )
    runs = (lying.run, turn.runs[1])
    broken = replace(turn, runs=runs)

    async def scenario(db: Database) -> None:
        with pytest.raises(ValidationError, match="cal_vigia1"):
            await answer_turn(db, broken, [lying, results[1]], calls)

    pg.run(scenario)
    assert pg.fetch("SELECT 1 FROM carmen.agent_runs") == []


def test_the_turn_status_must_be_the_answer_status(pg: Pg) -> None:
    turn = direct_turn(QUESTION)

    async def save_over_a_failed_answer(db: Database) -> None:
        async with db.unit_of_work():
            await store_messages(db, turn, [], status=TurnStatus.FAILED)
            await PgTurnRepository().save(turn, message_id=ANSWER)

    async def scenario(db: Database) -> None:
        with pytest.raises(ValidationError, match="estado"):
            await save_over_a_failed_answer(db)

    pg.run(scenario)


# --- Aprobaciones ------------------------------------------------------------------------


def request(n: int = 1, *, expires: float = 600) -> HumanApprovalRequest:
    return HumanApprovalRequest(
        request_id=ApprovalId(f"apr_{n:04d}"),
        turn_id=TURN,
        agent_id=VIGIA,
        action="exportar_informe",
        impact=Impact.HIGH,
        summary="Exportar el informe de monitores en KO",
        evidence_refs=(EvidenceReference(VIGIA_CALL, evidence_fact().fact_id),),
        required_role=Role.MANAGER,
        expires_at=at(expires),
    )


def test_an_approval_leaves_pending_once_and_never_goes_back(pg: Pg) -> None:
    repo = PgApprovalRepository(FrozenClock())

    async def expire_by_hand(db: Database) -> None:
        async with db.unit_of_work():
            await repo.create(request(2))
            await repo.decide(ApprovalId("apr_0002"), ApprovalStatus.EXPIRED, MANAGER, at(1))

    async def scenario(db: Database) -> None:
        async with db.unit_of_work():
            created = await repo.create(request())
            assert created == ApprovalRecord(
                ApprovalId("apr_0001"), ApprovalStatus.PENDING, request().evidence_refs
            )
            approved = await repo.decide(
                ApprovalId("apr_0001"), ApprovalStatus.APPROVED, MANAGER, at(10)
            )
        assert approved.decided_by == MANAGER
        assert approved.decided_at == at(10)
        for status in (ApprovalStatus.REJECTED, ApprovalStatus.APPROVED):
            with pytest.raises(InvalidTransitionError):
                async with db.unit_of_work():
                    await repo.decide(ApprovalId("apr_0001"), status, MANAGER, at(11))
        with pytest.raises(InvalidTransitionError, match="decisión"):
            await expire_by_hand(db)
        with pytest.raises(ValidationError, match="ya existe"):
            async with db.unit_of_work():
                await repo.create(request())
        with pytest.raises(ValidationError, match="no existe"):
            async with db.unit_of_work():
                await repo.decide(ApprovalId("apr_9999"), ApprovalStatus.APPROVED, MANAGER, at(1))
        async with db.unit_of_work():
            assert await repo.get(ApprovalId("apr_0001")) == approved
            assert await repo.get(ApprovalId("apr_9999")) is None

    pg.run(scenario)


def test_approvals_expire_in_one_statement_and_cannot_be_decided_late(pg: Pg) -> None:
    repo = PgApprovalRepository(FrozenClock())

    async def scenario(db: Database) -> None:
        async with db.unit_of_work():
            await repo.create(request(1, expires=60))
            await repo.create(request(2, expires=60))
            await repo.create(request(3, expires=900))
        with pytest.raises(InvalidTransitionError):
            async with db.unit_of_work():
                await repo.decide(ApprovalId("apr_0001"), ApprovalStatus.APPROVED, MANAGER, at(60))
        async with db.unit_of_work():
            assert await repo.expire_due(at(120)) == (
                ApprovalId("apr_0001"),
                ApprovalId("apr_0002"),
            )
            assert await repo.expire_due(at(120)) == ()
            expired = await repo.get(ApprovalId("apr_0002"))
        assert expired is not None
        assert expired.status is ApprovalStatus.EXPIRED

    pg.run(scenario)


def test_the_database_refuses_moving_an_approval_back_to_pending(pg: Pg) -> None:
    repo = PgApprovalRepository(FrozenClock())

    async def scenario(db: Database) -> None:
        async with db.unit_of_work():
            await repo.create(request())
            await repo.decide(ApprovalId("apr_0001"), ApprovalStatus.REJECTED, MANAGER, at(5))

    pg.run(scenario)
    with pytest.raises(asyncpg.CheckViolationError, match="solo se sale de pending"):
        pg.fetch(
            "UPDATE carmen.approvals SET status = 'pending', decided_by = NULL,"
            " decided_at = NULL WHERE id = 'apr_0001'"
        )
    with pytest.raises(asyncpg.CheckViolationError, match="ck_decided"):
        pg.fetch("UPDATE carmen.approvals SET decided_by = NULL WHERE id = 'apr_0001'")


def test_a_turn_carries_its_approvals_as_stored(pg: Pg) -> None:
    task = agent_task(1, VIGIA)
    plan = delegation_plan(task, requires_human_approval=True)
    approvals = PgApprovalRepository(FrozenClock())
    calls = [call(VIGIA_CALL, VIGIA_SYSTEM)]

    async def scenario(db: Database) -> ConversationTurn | None:
        async with db.unit_of_work():
            await approvals.create(request())
            record = await approvals.decide(
                ApprovalId("apr_0001"), ApprovalStatus.APPROVED, MANAGER, at(4)
            )
        result = replace(
            agent_result(task, evidence=(evidence_fact(call_id=VIGIA_CALL),)),
            run=replace(agent_result(task).run, tool_calls=(trace(calls[0]),), approvals=(record,)),
        )
        turn = replace(delegated_turn(plan, [result], question=QUESTION), approvals=(record,))
        await answer_turn(db, turn, [result], calls)
        with pytest.raises(ValidationError, match="apr_0001"):
            async with db.unit_of_work():
                await PgTurnRepository().save(
                    replace(turn, approvals=(replace(record, decided_by=PRINCIPAL),)),
                    message_id=ANSWER,
                    results=[result],
                )
        async with db.unit_of_work():
            loaded = await PgTurnRepository().get(TURN)
        assert loaded == turn
        return loaded

    assert pg.run(scenario) is not None
    assert pg.fetch("SELECT agent_run_id FROM carmen.approvals")[0]["agent_run_id"] == (
        "run_t1vigia"
    )


# --- Ciclo de vida -----------------------------------------------------------------------


def entry(state: AgentLifecycleState, seconds: float, **kw: object) -> AgentLifecycleEntry:
    return AgentLifecycleEntry(VIGIA, state, "1.4.0", at(seconds), **kw)  # type: ignore[arg-type]


def test_lifecycle_history_records_every_transition_with_actor_and_reason(pg: Pg) -> None:
    repo = PgAgentLifecycleRepository()
    admin = PrincipalId("usr_adm1")
    certified = entry(
        AgentLifecycleState.CERTIFIED,
        3,
        owner="equipo-vigia",
        certified_at=at(3),
        report_ref="cert/vigia/2026-10.pdf",
    )

    async def scenario(db: Database) -> None:
        async with db.unit_of_work():
            await repo.register(entry(AgentLifecycleState.DISCOVERED, 0), admin)
        async with db.unit_of_work():
            await repo.transition(entry(AgentLifecycleState.COMPATIBLE, 1), "contrato ok", admin)
            await repo.transition(certified, "batería 7.11.3 superada", admin)
        async with db.unit_of_work():
            quarantined = await repo.transition(
                entry(AgentLifecycleState.QUARANTINED, 9), "SLO roto", PRINCIPAL
            )
        assert quarantined.from_state is AgentLifecycleState.CERTIFIED
        with pytest.raises(InvalidTransitionError, match=r"7\.11\.2"):
            async with db.unit_of_work():
                await repo.transition(certified, "atajo", admin)
        with pytest.raises(ValidationError, match="ya está registrado"):
            async with db.unit_of_work():
                await repo.register(entry(AgentLifecycleState.DISCOVERED, 10), admin)
        with pytest.raises(InvalidTransitionError, match="DISCOVERED"):
            async with db.unit_of_work():
                await repo.register(
                    replace(entry(AgentLifecycleState.COMPATIBLE, 0), agent_id=PLENDATA), admin
                )
        with pytest.raises(ValidationError, match="no está registrado"):
            async with db.unit_of_work():
                await repo.transition(
                    replace(entry(AgentLifecycleState.COMPATIBLE, 0), agent_id=PLENDATA),
                    "contrato ok",
                    admin,
                )
        async with db.unit_of_work():
            current = await repo.get(VIGIA)
            history = await repo.history(VIGIA)
            assert await repo.get(PLENDATA) is None
        assert current == entry(AgentLifecycleState.QUARANTINED, 9)
        assert [(c.from_state, c.to_state, c.reason, c.actor) for c in history] == [
            (AgentLifecycleState.CERTIFIED, AgentLifecycleState.QUARANTINED, "SLO roto", PRINCIPAL),
            (
                AgentLifecycleState.COMPATIBLE,
                AgentLifecycleState.CERTIFIED,
                "batería 7.11.3 superada",
                admin,
            ),
            (AgentLifecycleState.DISCOVERED, AgentLifecycleState.COMPATIBLE, "contrato ok", admin),
            (None, AgentLifecycleState.DISCOVERED, "alta", admin),
        ]
        assert history[0].at == at(9)

    pg.run(scenario)


def test_the_database_refuses_a_certified_agent_without_its_report(pg: Pg) -> None:
    with pytest.raises(asyncpg.CheckViolationError, match="ck_certified"):
        pg.fetch(
            "INSERT INTO carmen.agent_lifecycle (agent_id, state, version, updated_at)"
            " VALUES ('agent.vigia', 'CERTIFIED', '1.0.0', now())"
        )


# --- Cobertura de la conversión del plan ------------------------------------------------


def test_a_single_agent_turn_with_a_failed_run_round_trips(pg: Pg) -> None:
    task = agent_task(1, VIGIA, entities={"estacion": "Alcorcón", "periodo": "hoy"}, deps=())
    failed = replace(
        agent_result(task, AgentResultStatus.FAILED),
        run=replace(
            agent_result(task).run, tool_calls=(trace(call(VIGIA_CALL, VIGIA_SYSTEM, ok=False)),)
        ),
    )
    plan = delegation_plan(task)
    turn = replace(
        delegated_turn(plan, [failed], question=QUESTION),
        status=TurnStatus.FAILED,
        tokens=TokenUsage(0, 0),
    )
    assert turn.response_mode is ResponseMode.DELEGATE_SINGLE

    async def scenario(db: Database) -> ConversationTurn | None:
        await answer_turn(db, turn, [failed], [call(VIGIA_CALL, VIGIA_SYSTEM, ok=False)])
        async with db.unit_of_work():
            return await PgTurnRepository().get(TURN)

    assert pg.run(scenario) == turn
    assert pg.fetch("SELECT status::text FROM carmen.agent_runs")[0]["status"] == "failed"
