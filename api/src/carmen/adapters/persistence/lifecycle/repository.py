"""AgentLifecycleRepository sobre PostgreSQL: estado e historial en la misma transacción (7.11)."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert

from carmen.adapters.persistence.engine import connection
from carmen.adapters.persistence.lifecycle import mappers
from carmen.adapters.persistence.lifecycle.tables import agent_lifecycle, agent_lifecycle_history
from carmen.application.ports.repositories import AgentLifecycleEntry, LifecycleChange
from carmen.domain.agents.card import AgentLifecycleState
from carmen.domain.errors import InvalidTransitionError, ValidationError
from carmen.domain.ids import AgentId, PrincipalId

#: Motivo de la primera fila del historial, la del alta.
REGISTRATION_REASON = "alta"


class PgAgentLifecycleRepository:
    async def register(self, entry: AgentLifecycleEntry, actor: PrincipalId) -> None:
        if entry.state is not AgentLifecycleState.DISCOVERED:
            msg = f"{entry.agent_id}: un agente nuevo entra en DISCOVERED (7.11.2)"
            raise InvalidTransitionError(msg)
        created = await connection().scalar(
            insert(agent_lifecycle)
            .values(mappers.entry_values(entry))
            .on_conflict_do_nothing(index_elements=[agent_lifecycle.c.agent_id])
            .returning(agent_lifecycle.c.agent_id)
        )
        if created is None:
            msg = f"{entry.agent_id} ya está registrado"
            raise ValidationError(msg)
        await self._log(
            LifecycleChange(
                entry.agent_id, None, entry.state, REGISTRATION_REASON, actor, entry.updated_at
            )
        )

    async def get(self, agent_id: AgentId) -> AgentLifecycleEntry | None:
        return await self._get(agent_id, lock=False)

    async def transition(
        self, entry: AgentLifecycleEntry, reason: str, actor: PrincipalId
    ) -> LifecycleChange:
        current = await self._get(entry.agent_id, lock=True)
        if current is None:
            msg = f"{entry.agent_id} no está registrado"
            raise ValidationError(msg)
        if not current.state.can_transition_to(entry.state):
            msg = f"{entry.agent_id}: {current.state} -> {entry.state} no está en 7.11.2"
            raise InvalidTransitionError(msg)
        values = mappers.entry_values(entry)
        del values["agent_id"]
        await connection().execute(
            sa.update(agent_lifecycle)
            .where(agent_lifecycle.c.agent_id == str(entry.agent_id))
            .values(values)
        )
        return await self._log(
            LifecycleChange(
                entry.agent_id, current.state, entry.state, reason, actor, entry.updated_at
            )
        )

    async def history(self, agent_id: AgentId) -> tuple[LifecycleChange, ...]:
        rows = await connection().execute(
            sa.select(agent_lifecycle_history)
            .where(agent_lifecycle_history.c.agent_id == str(agent_id))
            .order_by(agent_lifecycle_history.c.at.desc(), agent_lifecycle_history.c.seq.desc())
        )
        return tuple(mappers.change_from_row(r) for r in rows.mappings())

    async def _get(self, agent_id: AgentId, *, lock: bool) -> AgentLifecycleEntry | None:
        statement = sa.select(agent_lifecycle).where(agent_lifecycle.c.agent_id == str(agent_id))
        if lock:
            statement = statement.with_for_update()
        row = (await connection().execute(statement)).mappings().one_or_none()
        return None if row is None else mappers.entry_from_row(row)

    async def _log(self, change: LifecycleChange) -> LifecycleChange:
        await connection().execute(
            sa.insert(agent_lifecycle_history).values(mappers.change_values(change))
        )
        return change
