"""GlossaryRepository sobre PostgreSQL: cambio e historial en la misma transacción (7.8.4)."""

from dataclasses import replace

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert

from carmen.adapters.persistence.engine import connection
from carmen.adapters.persistence.glossary import mappers
from carmen.adapters.persistence.glossary.tables import glossary_history, glossary_terms
from carmen.adapters.persistence.types import as_text
from carmen.application.ports.repositories import GlossaryAction, GlossaryChange, GlossaryTerm
from carmen.domain.errors import ValidationError
from carmen.domain.ids import PrincipalId
from carmen.domain.time import Instant

_TERM_COLUMNS = (
    glossary_terms.c.term,
    glossary_terms.c.display,
    glossary_terms.c.definition,
    glossary_terms.c.aliases,
    glossary_terms.c.canonical,
    glossary_terms.c.active,
    glossary_terms.c.source,
)


class PgGlossaryRepository:
    async def list_active(self) -> tuple[GlossaryTerm, ...]:
        rows = await connection().execute(
            sa.select(*_TERM_COLUMNS).where(glossary_terms.c.active).order_by(glossary_terms.c.term)
        )
        return tuple(mappers.term_from_row(r) for r in rows.mappings())

    async def get(self, term: str) -> GlossaryTerm | None:
        return await self._get(term, lock=False)

    async def _get(self, term: str, *, lock: bool) -> GlossaryTerm | None:
        statement = sa.select(*_TERM_COLUMNS).where(glossary_terms.c.term == term)
        if lock:
            statement = statement.with_for_update()
        row = (await connection().execute(statement)).mappings().one_or_none()
        return None if row is None else mappers.term_from_row(row)

    async def upsert(self, t: GlossaryTerm, actor: PrincipalId, at: Instant) -> GlossaryChange:
        before = await self._get(t.term, lock=True)
        action = GlossaryAction.CREATE if before is None else GlossaryAction.UPDATE
        statement = insert(glossary_terms).values(mappers.term_values(t, actor, at))
        excluded = statement.excluded
        await connection().execute(
            statement.on_conflict_do_update(
                index_elements=[glossary_terms.c.term],
                set_={
                    "display": excluded.display,
                    "definition": excluded.definition,
                    "aliases": excluded.aliases,
                    "canonical": excluded.canonical,
                    "active": excluded.active,
                    "source": excluded.source,
                    "updated_by": excluded.updated_by,
                    "updated_at": excluded.updated_at,
                },
            )
        )
        return await self._log(GlossaryChange(t.term, action, actor, at, before=before, after=t))

    async def deactivate(self, term: str, actor: PrincipalId, at: Instant) -> GlossaryChange:
        """No se borra: se marca inactivo y el historial conserva cómo era."""
        before = await self._get(term, lock=True)
        if before is None or not before.active:
            msg = f"el término {term!r} no existe o ya está inactivo"
            raise ValidationError(msg)
        await connection().execute(
            sa.update(glossary_terms)
            .where(glossary_terms.c.term == term)
            .values(active=False, updated_by=str(actor), updated_at=at.at)
        )
        after = replace(before, active=False)
        return await self._log(
            GlossaryChange(term, GlossaryAction.DEACTIVATE, actor, at, before, after)
        )

    async def history(self, term: str) -> tuple[GlossaryChange, ...]:
        rows = await connection().execute(
            sa.select(
                glossary_history.c.term,
                glossary_history.c.action,
                as_text(glossary_history.c.before).label("before"),
                as_text(glossary_history.c.after).label("after"),
                glossary_history.c.actor,
                glossary_history.c.at,
            )
            .where(glossary_history.c.term == term)
            .order_by(glossary_history.c.at, glossary_history.c.seq)
        )
        return tuple(mappers.change_from_row(r) for r in rows.mappings())

    async def _log(self, change: GlossaryChange) -> GlossaryChange:
        await connection().execute(sa.insert(glossary_history).values(mappers.history_row(change)))
        return change
