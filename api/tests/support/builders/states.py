"""Turnos completos (6.12.8): directo, delegado y con agentes ausentes."""

from collections.abc import Sequence
from decimal import Decimal

from carmen.domain.conversation.turn import ConversationTurn, TokenUsage, TurnStatus
from carmen.domain.delegation.models import AgentResult, AgentResultStatus, DelegationPlan
from carmen.domain.ids import AgentId, TurnId
from carmen.domain.orchestration.mode import ResponseMode
from support.builders.common import CONVERSATION, POLICY_VERSION, PRINCIPAL, TURN


def direct_turn(
    question: str = "Hola, buenos días",
    *,
    mode: ResponseMode = ResponseMode.SUPERVISOR_DIRECT,
    turn_id: TurnId = TURN,
    status: TurnStatus = TurnStatus.COMPLETED,
) -> ConversationTurn:
    return ConversationTurn(
        turn_id=turn_id,
        conversation_id=CONVERSATION,
        principal_id=PRINCIPAL,
        question=question,
        response_mode=mode,
        policy_version=POLICY_VERSION,
        status=status,
    )


def delegated_turn(
    plan: DelegationPlan,
    results: Sequence[AgentResult],
    *,
    question: str = "¿Cuántos monitores hay en KO?",
    missing: Sequence[AgentId] = (),
    latency_ms: int = 0,
) -> ConversationTurn:
    """El estado del turno se deduce de los resultados: un ausente o un parcial lo hacen parcial."""
    partial = bool(missing) or any(r.status is not AgentResultStatus.OK for r in results)
    return ConversationTurn(
        turn_id=plan.turn_id,
        conversation_id=CONVERSATION,
        principal_id=plan.principal_id,
        question=question,
        response_mode=plan.response_mode,
        policy_version=plan.policy_version,
        status=TurnStatus.PARTIAL if partial else TurnStatus.COMPLETED,
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
