"""Prompt 3: ficha del agente, modo de respuesta y ciclo de vida (2.3.2, 5.14.3, 7.11.2)."""

import itertools
from dataclasses import replace
from decimal import Decimal

import pytest

from carmen.domain.agents.card import (
    LIFECYCLE_TRANSITIONS,
    AgentBudgets,
    AgentCard,
    AgentLifecycleState,
    AgentSlo,
    AllowedAction,
    Connectivity,
    Visibility,
)
from carmen.domain.errors import InvalidTransitionError, ValidationError
from carmen.domain.ids import AgentId, McpServerId, Scope
from carmen.domain.orchestration.mode import ResponseMode

pytestmark = pytest.mark.domain

S = AgentLifecycleState


def vigia(status: AgentLifecycleState = S.CERTIFIED) -> AgentCard:
    return AgentCard(
        agent_id=AgentId("agent.vigia"),
        version="1.4.0",
        display_name="VigIA",
        owner="Operaciones de red",
        status=status,
        connectivity=Connectivity.INTERNAL_ONLY,
        visibility=Visibility.DISCOVERABLE,
        safe_description="Monitorización de la red de estaciones de servicio.",
        public_capabilities=("Consultar el estado actual de una estación",),
        routing_description="Estaciones, alarmas, monitores, disponibilidad, SLA.",
        allowed_actions=frozenset({AllowedAction.READ}),
        scopes=frozenset({Scope("vigia.read")}),
        entities_exposed=("estacion", "monitor", "alarma"),
        mcp_bindings=(McpServerId("mcp.vigia-ops"),),
        provider_bindings=(),
        slo=AgentSlo(p95_ms=6000, availability=Decimal("99.0")),
        budgets=AgentBudgets(6000, Decimal("0.00"), 25000),
        golden_set="eval/golden/vigia/*.yaml",
        kill_switch=True,
    )


def test_response_modes_are_the_five_of_2_3_2() -> None:
    assert [m.value for m in ResponseMode] == [
        "SUPERVISOR_DIRECT",
        "DELEGATE_SINGLE",
        "DELEGATE_MULTI",
        "CLARIFY",
        "REFUSE",
    ]
    assert {m for m in ResponseMode if m.delegates} == {
        ResponseMode.DELEGATE_SINGLE,
        ResponseMode.DELEGATE_MULTI,
    }


def test_the_vigia_card_of_5_14_3_builds() -> None:
    card = vigia()
    assert card.status.invocable
    assert not vigia(S.COMPATIBLE).status.invocable


def test_lifecycle_has_exactly_the_four_transitions_of_7_11_2() -> None:
    assert {(a.value, b.value) for a, b in LIFECYCLE_TRANSITIONS} == {
        ("DISCOVERED", "COMPATIBLE"),
        ("COMPATIBLE", "CERTIFIED"),
        ("CERTIFIED", "QUARANTINED"),
        ("QUARANTINED", "DISCOVERED"),
    }


@pytest.mark.parametrize(("source", "target"), sorted(LIFECYCLE_TRANSITIONS))
def test_allowed_transitions(source: AgentLifecycleState, target: AgentLifecycleState) -> None:
    assert vigia(source).transition_to(target).status is target


FORBIDDEN = sorted(set(itertools.product(S, S)) - LIFECYCLE_TRANSITIONS)


@pytest.mark.parametrize(("source", "target"), FORBIDDEN)
def test_every_other_transition_is_a_domain_error(
    source: AgentLifecycleState, target: AgentLifecycleState
) -> None:
    with pytest.raises(InvalidTransitionError):
        vigia(source).transition_to(target)


def test_quarantine_needs_a_new_certification_to_come_back() -> None:
    card = vigia().transition_to(S.QUARANTINED)
    with pytest.raises(InvalidTransitionError):
        card.transition_to(S.CERTIFIED)
    back = card.transition_to(S.DISCOVERED).transition_to(S.COMPATIBLE)
    assert back.transition_to(S.CERTIFIED).status.invocable


@pytest.mark.parametrize(
    "overrides",
    [
        {"version": "1.4"},
        {"owner": " "},
        {"safe_description": ""},
        {"public_capabilities": ("",)},
        {"allowed_actions": frozenset()},
        {"allowed_actions": frozenset({AllowedAction.READ, AllowedAction.WRITE})},
        {"mcp_bindings": (McpServerId("mcp.a1"), McpServerId("mcp.a1"))},
    ],
)
def test_malformed_cards(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        replace(vigia(), **overrides)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "build",
    [
        lambda: AgentSlo(-1, Decimal(99)),
        lambda: AgentSlo(100, Decimal(101)),
        lambda: AgentBudgets(-1, Decimal(0), 1),
        lambda: AgentBudgets(1, Decimal(-1), 1),
        lambda: AgentBudgets(1, Decimal("NaN"), 1),
        lambda: AgentBudgets(1, Decimal(0), True),
    ],
)
def test_malformed_slo_and_budgets(build: object) -> None:
    with pytest.raises(ValidationError):
        build()  # type: ignore[operator]
