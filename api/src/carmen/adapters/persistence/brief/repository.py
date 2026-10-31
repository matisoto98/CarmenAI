"""BriefRepository sobre PostgreSQL: una única fila que se sustituye (unidad de trabajo 5)."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert

from carmen.adapters.persistence.brief import mappers
from carmen.adapters.persistence.brief.tables import situation_brief
from carmen.adapters.persistence.engine import connection
from carmen.adapters.persistence.types import as_text, instant
from carmen.application.ports.repositories import SituationBrief

#: Valor de la única fila (CHECK id = 1).
SINGLE_ROW = 1


class PgBriefRepository:
    async def get(self) -> SituationBrief | None:
        result = await connection().execute(
            sa.select(as_text(situation_brief.c.payload), situation_brief.c.generated_at).where(
                situation_brief.c.id == SINGLE_ROW
            )
        )
        row = result.one_or_none()
        if row is None:
            return None
        payload, generated_at = row
        return mappers.brief_from_row(payload, instant(generated_at))

    async def put(self, b: SituationBrief) -> None:
        statement = insert(situation_brief).values(
            id=SINGLE_ROW,
            payload=mappers.brief_payload(b),
            generated_at=b.generated_at.at,
        )
        await connection().execute(
            statement.on_conflict_do_update(
                index_elements=[situation_brief.c.id],
                set_={
                    "payload": statement.excluded.payload,
                    "generated_at": statement.excluded.generated_at,
                },
            )
        )
