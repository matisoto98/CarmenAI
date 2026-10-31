"""Política: tabla ⇄ dominio."""

from dataclasses import dataclass

from sqlalchemy import RowMapping

from carmen.adapters.persistence.types import instant
from carmen.domain.ids import AgentId, PrincipalId, Scope, TurnId
from carmen.domain.policy.models import (
    AgentAction,
    Effect,
    PlatformAction,
    PolicyDecision,
    PolicyRole,
    Principal,
    RoleAgentGrant,
    RoleAssignment,
)
from carmen.domain.time import Instant


@dataclass(frozen=True, slots=True)
class ApplicableGrant:
    """Una concesión de uno de los roles del principal para la acción pedida."""

    agent_id: AgentId
    effect: Effect
    scopes: frozenset[Scope]


def principal_values(p: Principal, at: Instant) -> dict[str, object]:
    return {
        "id": str(p.principal_id),
        "directory_ref": p.directory_ref,
        "display_name": p.display_name,
        "active": p.active,
        "created_at": at.at,
        "updated_at": at.at,
    }


def role_values(r: PolicyRole) -> dict[str, object]:
    return {
        "id": str(r.role_id),
        "name": r.name,
        "platform_actions": sorted(a.value for a in r.platform_actions),
        "version": r.version,
    }


def assignment_values(a: RoleAssignment, at: Instant) -> dict[str, object]:
    return {
        "principal_id": str(a.principal_id),
        "role_id": str(a.role_id),
        "source": a.source.value,
        "granted_at": at.at,
    }


def grant_values(g: RoleAgentGrant) -> dict[str, object]:
    return {
        "role_id": str(g.role_id),
        "agent_id": str(g.agent_id),
        "actions": sorted(a.value for a in g.actions),
        "scopes": sorted(str(s) for s in g.scopes),
        "effect": g.effect.value,
        "reason": g.reason,
    }


def decision_values(d: PolicyDecision) -> dict[str, object]:
    return {
        "turn_id": str(d.turn_id),
        "principal_id": str(d.principal_id),
        "agent_id": None if d.agent_id is None else str(d.agent_id),
        "action": d.action.value,
        "decision": d.decision.value,
        "reason_code": d.reason_code,
        "policy_version": d.policy_version,
        "decided_at": d.decided_at.at,
        "scopes": sorted(str(s) for s in d.scopes),
    }


def decision_from_row(r: RowMapping) -> PolicyDecision:
    action: AgentAction | PlatformAction = (
        AgentAction(r["action"])
        if r["action"] in AgentAction._value2member_map_
        else PlatformAction(r["action"])
    )
    return PolicyDecision(
        turn_id=TurnId(r["turn_id"]),
        principal_id=PrincipalId(r["principal_id"]),
        action=action,
        decision=Effect(r["decision"]),
        reason_code=r["reason_code"],
        policy_version=r["policy_version"],
        decided_at=instant(r["decided_at"]),
        agent_id=None if r["agent_id"] is None else AgentId(r["agent_id"]),
        scopes=frozenset(Scope(s) for s in r["scopes"]),
    )


def applicable_from_row(r: RowMapping) -> ApplicableGrant:
    return ApplicableGrant(
        agent_id=AgentId(r["agent_id"]),
        effect=Effect(r["effect"]),
        scopes=frozenset(Scope(s) for s in r["scopes"]),
    )
