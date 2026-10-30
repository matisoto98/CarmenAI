"""Política persistida (7.9.7): PolicyPort sobre PostgreSQL y la escritura de sus tablas.

PgPolicy no es un repositorio de un agregado: decide en cualquier momento del turno, también
fuera de una unidad de trabajo, así que lee con su propia conexión corta de solo lectura. Si la
base no responde, deniega con motivo policy_unavailable: el puerto nunca lanza (5.14.4).

PgPolicyStore sí escribe dentro de la unidad de trabajo en curso, como cualquier repositorio.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import Executable, RowMapping
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

from carmen.adapters.persistence.engine import connection
from carmen.adapters.persistence.policy import mappers
from carmen.adapters.persistence.policy.mappers import ApplicableGrant
from carmen.adapters.persistence.policy.tables import (
    policy_decisions,
    principals,
    role_agent_grants,
    role_assignments,
    roles,
)
from carmen.application.ports.system import Clock
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

UNAVAILABLE = "policy_unavailable"

_ACTIVE_ROLES = (
    sa.select(role_assignments.c.role_id)
    .join(principals, principals.c.id == role_assignments.c.principal_id)
    .where(principals.c.active, principals.c.id == sa.bindparam("principal_id"))
)


class PolicyUnavailableError(RuntimeError):
    """La política no se pudo leer. No sale del adaptador: se convierte en una denegación."""


class PgPolicy:
    """Denegación por defecto; el deny explícito prevalece; allow une los scopes (7.9.3)."""

    def __init__(self, engine: AsyncEngine, *, version: str, clock: Clock) -> None:
        self._engine = engine
        self._version = version
        self._clock = clock

    def version(self) -> str:
        return self._version

    async def decide(
        self, *, principal_id: PrincipalId, action: AgentAction, agent_id: AgentId, turn_id: TurnId
    ) -> PolicyDecision:
        try:
            grants = await self._grants(principal_id, action, agent_id)
        except PolicyUnavailableError:
            return self._decision(turn_id, principal_id, action, Effect.DENY, UNAVAILABLE, agent_id)
        return self._resolve(turn_id, principal_id, action, agent_id, grants)

    async def decide_platform(
        self, *, principal_id: PrincipalId, action: PlatformAction, turn_id: TurnId
    ) -> PolicyDecision:
        statement = (
            sa.select(sa.literal(True))
            .select_from(roles)
            .where(
                roles.c.id.in_(_ACTIVE_ROLES),
                sa.literal(action.value) == sa.func.any(roles.c.platform_actions),
            )
            .limit(1)
        )
        try:
            granted = bool(await self._read(statement, principal_id))
        except PolicyUnavailableError:
            return self._decision(turn_id, principal_id, action, Effect.DENY, UNAVAILABLE)
        effect, reason = (Effect.ALLOW, "platform_role") if granted else (Effect.DENY, "no_role")
        return self._decision(turn_id, principal_id, action, effect, reason)

    async def allowed_agents(
        self, *, principal_id: PrincipalId, action: AgentAction, turn_id: TurnId
    ) -> tuple[PolicyDecision, ...]:
        try:
            grants = await self._grants(principal_id, action, None)
        except PolicyUnavailableError:
            return ()
        decisions = (
            self._resolve(
                turn_id, principal_id, action, agent, [g for g in grants if g.agent_id == agent]
            )
            for agent in sorted({g.agent_id for g in grants})
        )
        return tuple(d for d in decisions if d.allowed)

    def _resolve(
        self,
        turn_id: TurnId,
        principal_id: PrincipalId,
        action: AgentAction,
        agent_id: AgentId,
        grants: Sequence[ApplicableGrant],
    ) -> PolicyDecision:
        if any(g.effect is Effect.DENY for g in grants):
            return self._decision(
                turn_id, principal_id, action, Effect.DENY, "explicit_deny", agent_id
            )
        allows = [g for g in grants if g.effect is Effect.ALLOW]
        if not allows:
            return self._decision(turn_id, principal_id, action, Effect.DENY, "no_grant", agent_id)
        scopes: frozenset[Scope] = frozenset().union(*(g.scopes for g in allows))
        return self._decision(
            turn_id, principal_id, action, Effect.ALLOW, "grant", agent_id, scopes
        )

    async def _grants(
        self, principal_id: PrincipalId, action: AgentAction, agent_id: AgentId | None
    ) -> list[ApplicableGrant]:
        statement = sa.select(
            role_agent_grants.c.agent_id, role_agent_grants.c.effect, role_agent_grants.c.scopes
        ).where(
            role_agent_grants.c.role_id.in_(_ACTIVE_ROLES),
            sa.literal(action.value) == sa.func.any(role_agent_grants.c.actions),
        )
        if agent_id is not None:
            statement = statement.where(role_agent_grants.c.agent_id == str(agent_id))
        return [mappers.applicable_from_row(r) for r in await self._read(statement, principal_id)]

    async def _read(self, statement: Executable, principal_id: PrincipalId) -> Sequence[RowMapping]:
        try:
            async with self._engine.connect() as conn:
                result = await conn.execute(statement, {"principal_id": str(principal_id)})
                return result.mappings().all()
        except (SQLAlchemyError, OSError) as error:
            raise PolicyUnavailableError(str(error)) from error

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


class PgPolicyStore:
    """Escritura de la política y registro de decisiones, en la unidad de trabajo en curso.

    Guardar lo mismo dos veces sustituye la fila: la carga desde el directorio es repetible.
    """

    async def save_principal(self, p: Principal, at: Instant) -> None:
        statement = insert(principals).values(mappers.principal_values(p, at))
        excluded = statement.excluded
        await connection().execute(
            statement.on_conflict_do_update(
                index_elements=[principals.c.id],
                set_={
                    "directory_ref": excluded.directory_ref,
                    "display_name": excluded.display_name,
                    "active": excluded.active,
                    "updated_at": excluded.updated_at,
                },
            )
        )

    async def save_role(self, r: PolicyRole) -> None:
        statement = insert(roles).values(mappers.role_values(r))
        excluded = statement.excluded
        await connection().execute(
            statement.on_conflict_do_update(
                index_elements=[roles.c.id],
                set_={
                    "name": excluded.name,
                    "platform_actions": excluded.platform_actions,
                    "version": excluded.version,
                },
            )
        )

    async def assign(self, a: RoleAssignment, at: Instant) -> None:
        statement = insert(role_assignments).values(mappers.assignment_values(a, at))
        await connection().execute(
            statement.on_conflict_do_update(
                index_elements=[role_assignments.c.principal_id, role_assignments.c.role_id],
                set_={"source": statement.excluded.source},
            )
        )

    async def grant(self, g: RoleAgentGrant) -> None:
        statement = insert(role_agent_grants).values(mappers.grant_values(g))
        excluded = statement.excluded
        await connection().execute(
            statement.on_conflict_do_update(
                index_elements=[role_agent_grants.c.role_id, role_agent_grants.c.agent_id],
                set_={
                    "actions": excluded.actions,
                    "scopes": excluded.scopes,
                    "effect": excluded.effect,
                    "reason": excluded.reason,
                },
            )
        )

    async def record(self, d: PolicyDecision) -> None:
        """Paso 5 de 7.9.3: toda decisión queda registrada con la versión de política usada."""
        await connection().execute(sa.insert(policy_decisions).values(mappers.decision_values(d)))
