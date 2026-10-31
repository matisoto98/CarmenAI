"""Prompt 3: ConversationTurn y TurnStatus (6.12.8)."""

from dataclasses import replace
from decimal import Decimal

import pytest

from carmen.domain.conversation.turn import ConversationTurn, TokenUsage, TurnStatus
from carmen.domain.delegation.models import (
    AgentRun,
    AgentTask,
    Budgets,
    Composition,
    CompositionKind,
    DelegationPlan,
    Expects,
    TaskBudgets,
)
from carmen.domain.errors import ValidationError
from carmen.domain.ids import (
    AgentId,
    ConversationId,
    DelegatedIdentityRef,
    DelegationPlanId,
    PrincipalId,
    RunId,
    TaskId,
    TurnId,
)
from carmen.domain.locale import Locale
from carmen.domain.orchestration.mode import ResponseMode
from carmen.domain.time import Instant

pytestmark = pytest.mark.domain

TURN = TurnId("trn_18ab44de")
VIGIA = AgentId("agent.vigia")
NOW = Instant.parse("2026-07-27T09:14:22Z")


def greeting(**overrides: object) -> ConversationTurn:
    fields: dict[str, object] = {
        "turn_id": TURN,
        "conversation_id": ConversationId("cnv_0001"),
        "principal_id": PrincipalId("usr_a91f"),
        "question": "Hola, buenos días",
        "response_mode": ResponseMode.SUPERVISOR_DIRECT,
        "policy_version": "pol-2026-07-21",
        "status": TurnStatus.COMPLETED,
    }
    fields.update(overrides)
    return ConversationTurn(**fields)  # type: ignore[arg-type]


def single_plan(turn: TurnId = TURN) -> DelegationPlan:
    return DelegationPlan(
        plan_id=DelegationPlanId("dpl_7a3b9c1e4f20"),
        turn_id=turn,
        response_mode=ResponseMode.DELEGATE_SINGLE,
        principal_id=PrincipalId("usr_a91f"),
        policy_version="pol-2026-07-21",
        tasks=(
            AgentTask(
                TaskId("t1"),
                VIGIA,
                "alarmas abiertas en Getafe",
                {"estacion": "1"},
                Expects.FACTS,
                Locale.ES,
                TaskBudgets(10000, 6000, Decimal(0)),
                DelegatedIdentityRef("idr_7f3a9c1e2b40"),
            ),
        ),
        composition=Composition(CompositionKind.SINGLE, (TaskId("t1"),)),
        budgets=Budgets(20000, 14000, Decimal(0), max_agents=3),
    )


RUN = AgentRun(RunId("run_0001"), VIGIA, NOW, NOW)


def test_a_greeting_is_a_direct_turn_with_no_cost() -> None:
    turn = greeting()
    assert turn.agents_used == ()
    assert turn.delegation_plan is None
    assert turn.cost_eur == 0
    assert turn.tokens.total == 0


@pytest.mark.parametrize("mode", [ResponseMode.SUPERVISOR_DIRECT, ResponseMode.CLARIFY])
@pytest.mark.parametrize(
    "overrides",
    [
        {"agents_used": (VIGIA,)},
        {"delegation_plan": single_plan()},
        {"runs": (RUN,)},
        {"missing_agents": (VIGIA,)},
        {"redelegations": 1},
    ],
)
def test_non_delegating_turns_touch_no_agent(
    mode: ResponseMode, overrides: dict[str, object]
) -> None:
    with pytest.raises(ValidationError):
        greeting(response_mode=mode, **overrides)


def test_refusal_is_recorded_too() -> None:
    assert greeting(response_mode=ResponseMode.REFUSE, status=TurnStatus.REJECTED)


def test_delegated_turn() -> None:
    turn = greeting(
        question="¿Cuántas alarmas tiene Getafe?",
        response_mode=ResponseMode.DELEGATE_SINGLE,
        delegation_plan=single_plan(),
        agents_used=(VIGIA,),
        runs=(RUN,),
        tokens=TokenUsage(900, 120),
        latency_ms=2400,
        redelegations=1,
    )
    assert turn.tokens.total == 1020


@pytest.mark.parametrize(
    "overrides",
    [
        {"delegation_plan": None},
        {"delegation_plan": single_plan(TurnId("trn_otro0001"))},
        {"response_mode": ResponseMode.DELEGATE_MULTI},
        {"agents_used": ()},
        {"missing_agents": (VIGIA,)},
        {"redelegations": 2},
        {"agents_used": (VIGIA, VIGIA)},
    ],
)
def test_incoherent_delegated_turns(overrides: dict[str, object]) -> None:
    fields: dict[str, object] = {
        "response_mode": ResponseMode.DELEGATE_SINGLE,
        "delegation_plan": single_plan(),
        "agents_used": (VIGIA,),
        "runs": (RUN,),
    }
    fields.update(overrides)
    with pytest.raises(ValidationError):
        greeting(**fields)


@pytest.mark.parametrize(
    "overrides",
    [
        {"question": " "},
        {"policy_version": ""},
        {"latency_ms": -1},
        {"cost_eur": Decimal(-1)},
        {"cost_eur": Decimal("NaN")},
    ],
)
def test_malformed_turns(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        greeting(**overrides)


def test_token_usage_rejects_negatives() -> None:
    with pytest.raises(ValidationError):
        TokenUsage(-1, 0)
    with pytest.raises(ValidationError):
        replace(TokenUsage(), tokens_out=-5)


def test_turn_status_matches_msg_status() -> None:
    assert [s.value for s in TurnStatus] == [
        "completed",
        "partial",
        "rejected",
        "failed",
        "cancelled",
        "no_data",
    ]
