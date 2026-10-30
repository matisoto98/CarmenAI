"""Prompt 3: principal, roles, concesiones y decisiones de política (7.9.2)."""

import pytest

from carmen.domain.errors import ValidationError
from carmen.domain.ids import AgentId, PrincipalId, RoleId, Scope, TurnId
from carmen.domain.policy.models import (
    AgentAction,
    AssignmentSource,
    Effect,
    PlatformAction,
    PolicyDecision,
    PolicyRole,
    Principal,
    RoleAgentGrant,
    RoleAssignment,
)
from carmen.domain.time import Instant

pytestmark = pytest.mark.domain

NOW = Instant.parse("2026-07-28T10:00:00Z")
PLENDATA = AgentId("agent.plendata")
TURN = TurnId("trn_18ab44de")
USER = PrincipalId("usr_a91f")


def test_policy_entities_of_7_9_6() -> None:
    admin = PolicyRole(
        RoleId("carmen.admin"),
        "Administración de la plataforma",
        frozenset({PlatformAction.CARMEN_ADMIN, PlatformAction.POLICY_WRITE}),
        "pol-2026-07-28",
    )
    assert PlatformAction.AUDIT_READ not in admin.platform_actions
    principal = Principal(USER, "entra:oid-1", "Ana", active=True)
    assignment = RoleAssignment(principal.principal_id, admin.role_id, AssignmentSource.DIRECTORY)
    assert assignment.source == "directory"
    grant = RoleAgentGrant(
        RoleId("ops.operator"),
        AgentId("agent.vigia"),
        frozenset({AgentAction.DISCOVER, AgentAction.DESCRIBE, AgentAction.INVOKE}),
        Effect.ALLOW,
        frozenset({Scope("vigia.read.limited")}),
    )
    assert grant.reason is None


@pytest.mark.parametrize("reason", [None, "", "  "])
def test_a_deny_without_reason_cannot_be_built(reason: str | None) -> None:
    with pytest.raises(ValidationError, match="motivo"):
        RoleAgentGrant(
            RoleId("proveedor.externo"),
            PLENDATA,
            frozenset({AgentAction.INVOKE}),
            Effect.DENY,
            reason=reason,
        )


def test_explicit_deny_with_reason() -> None:
    grant = RoleAgentGrant(
        RoleId("proveedor.externo"),
        PLENDATA,
        frozenset({AgentAction.DISCOVER, AgentAction.DESCRIBE, AgentAction.INVOKE}),
        Effect.DENY,
        reason="Proveedor externo sin acceso a información económica",
    )
    assert grant.effect is Effect.DENY


def test_grant_needs_actions() -> None:
    with pytest.raises(ValidationError):
        RoleAgentGrant(RoleId("r"), PLENDATA, frozenset(), Effect.ALLOW)


@pytest.mark.parametrize(
    "build",
    [
        lambda: Principal(USER, "", "Ana", active=True),
        lambda: Principal(USER, "entra:1", " ", active=True),
        lambda: PolicyRole(RoleId("r"), "", frozenset(), "v1"),
        lambda: PolicyRole(RoleId("r"), "Rol", frozenset(), ""),
    ],
)
def test_malformed_principal_and_role(build: object) -> None:
    with pytest.raises(ValidationError):
        build()  # type: ignore[operator]


def decision(**overrides: object) -> PolicyDecision:
    fields: dict[str, object] = {
        "turn_id": TURN,
        "principal_id": USER,
        "action": AgentAction.INVOKE,
        "decision": Effect.ALLOW,
        "reason_code": "grant_allow",
        "policy_version": "pol-2026-07-28",
        "decided_at": NOW,
        "agent_id": PLENDATA,
        "scopes": frozenset({Scope("plendata.read")}),
    }
    fields.update(overrides)
    return PolicyDecision(**fields)  # type: ignore[arg-type]


def test_policy_decisions() -> None:
    assert decision().allowed
    denied = decision(decision=Effect.DENY, reason_code="explicit_deny", scopes=frozenset())
    assert not denied.allowed
    platform = decision(action=PlatformAction.KPIS_READ, agent_id=None, scopes=frozenset())
    assert platform.allowed


@pytest.mark.parametrize(
    "overrides",
    [
        {"reason_code": ""},
        {"policy_version": " "},
        {"agent_id": None},
        {"action": PlatformAction.KPIS_READ},
        {"decision": Effect.DENY, "reason_code": "default_deny"},
    ],
)
def test_malformed_decisions(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        decision(**overrides)
