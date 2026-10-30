"""Política en memoria con el algoritmo de 7.9.3."""

from collections.abc import Iterable

from carmen.application.ports.system import Clock
from carmen.domain.ids import AgentId, PrincipalId, RoleId, Scope, TurnId
from carmen.domain.policy.models import (
    AgentAction,
    Effect,
    PlatformAction,
    PolicyDecision,
    PolicyRole,
    RoleAgentGrant,
    RoleAssignment,
)
from support.fakes.system import FrozenClock


class InMemoryPolicy:
    """Denegación por defecto; el deny explícito prevalece; allow une los scopes.

    No sabe qué agentes existen: un agente inexistente y uno oculto reciben la misma
    denegación, sin ningún trabajo adicional (7.9.5).
    """

    def __init__(
        self,
        *,
        version: str,
        roles: Iterable[PolicyRole] = (),
        assignments: Iterable[RoleAssignment] = (),
        grants: Iterable[RoleAgentGrant] = (),
        clock: Clock | None = None,
    ) -> None:
        self._version = version
        self._roles = {r.role_id: r for r in roles}
        self._assignments = tuple(assignments)
        self._grants = tuple(grants)
        self._clock = clock or FrozenClock()

    def version(self) -> str:
        return self._version

    def _roles_of(self, principal_id: PrincipalId) -> frozenset[RoleId]:
        return frozenset(a.role_id for a in self._assignments if a.principal_id == principal_id)

    async def decide(
        self, *, principal_id: PrincipalId, action: AgentAction, agent_id: AgentId, turn_id: TurnId
    ) -> PolicyDecision:
        roles = self._roles_of(principal_id)
        applicable = [
            g
            for g in self._grants
            if g.role_id in roles and g.agent_id == agent_id and action in g.actions
        ]
        if any(g.effect is Effect.DENY for g in applicable):
            return self._decision(
                turn_id, principal_id, action, Effect.DENY, "explicit_deny", agent_id
            )
        allows = [g for g in applicable if g.effect is Effect.ALLOW]
        if not allows:
            return self._decision(turn_id, principal_id, action, Effect.DENY, "no_grant", agent_id)
        scopes: frozenset[Scope] = frozenset().union(*(g.scopes for g in allows))
        return self._decision(
            turn_id, principal_id, action, Effect.ALLOW, "grant", agent_id, scopes
        )

    async def decide_platform(
        self, *, principal_id: PrincipalId, action: PlatformAction, turn_id: TurnId
    ) -> PolicyDecision:
        granted = any(
            action in self._roles[r].platform_actions
            for r in self._roles_of(principal_id)
            if r in self._roles
        )
        effect, reason = (Effect.ALLOW, "platform_role") if granted else (Effect.DENY, "no_role")
        return self._decision(turn_id, principal_id, action, effect, reason)

    async def allowed_agents(
        self, *, principal_id: PrincipalId, action: AgentAction, turn_id: TurnId
    ) -> tuple[PolicyDecision, ...]:
        roles = self._roles_of(principal_id)
        candidates = sorted({g.agent_id for g in self._grants if g.role_id in roles})
        decisions = [
            await self.decide(
                principal_id=principal_id, action=action, agent_id=agent, turn_id=turn_id
            )
            for agent in candidates
        ]
        return tuple(d for d in decisions if d.allowed)

    def _decision(
        self,
        turn_id: TurnId,
        principal_id: PrincipalId,
        action: AgentAction | PlatformAction,
        effect: Effect,
        reason_code: str,
        agent_id: AgentId | None = None,
        scopes: frozenset[Scope] = frozenset(),
    ) -> PolicyDecision:
        return PolicyDecision(
            turn_id=turn_id,
            principal_id=principal_id,
            action=action,
            decision=effect,
            reason_code=reason_code,
            policy_version=self._version,
            decided_at=self._clock.now(),
            agent_id=agent_id,
            scopes=scopes,
        )
