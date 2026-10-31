"""GapRepository sobre PostgreSQL (unidad de trabajo 2 de 7.4)."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import aggregate_order_by, insert

from carmen.adapters.persistence.engine import connection
from carmen.adapters.persistence.gaps import mappers
from carmen.adapters.persistence.gaps.tables import gaps
from carmen.application.ports.repositories import GapCluster, GapDraft, GapFilter, GapId
from carmen.application.ports.system import IdGenerator


class PgGapRepository:
    def __init__(self, ids: IdGenerator) -> None:
        self._ids = ids

    async def record(self, g: GapDraft) -> GapId:
        """INSERT … ON CONFLICT DO UPDATE: el incremento lo hace la base, sin leer antes."""
        statement = insert(gaps).values(mappers.gap_row(GapId(f"gap_{self._ids.new_id()}"), g))
        upsert = statement.on_conflict_do_update(
            index_elements=[gaps.c.question_norm, gaps.c.locale],
            set_={
                "occurrences": gaps.c.occurrences + 1,
                "last_seen": sa.func.greatest(gaps.c.last_seen, statement.excluded.last_seen),
            },
        ).returning(gaps.c.id)
        return GapId((await connection().execute(upsert)).scalar_one())

    async def list_clusters(self, f: GapFilter) -> list[GapCluster]:
        """Una laguna sin agrupar es su propio grupo; las de un mismo cluster_id, uno solo."""
        group = sa.func.coalesce(sa.cast(gaps.c.cluster_id, sa.Text), gaps.c.id)
        conditions = []
        if f.status is not None:
            conditions.append(gaps.c.status == f.status.value)
        if f.locale is not None:
            conditions.append(gaps.c.locale == f.locale.value)
        occurrences = sa.func.sum(gaps.c.occurrences)
        rows = await connection().execute(
            sa.select(
                sa.func.max(gaps.c.cluster_name).label("cluster_name"),
                gaps.c.locale,
                sa.func.array_agg(
                    aggregate_order_by(gaps.c.question, gaps.c.occurrences.desc(), gaps.c.question)
                ).label("questions"),
                occurrences.label("occurrences"),
                sa.func.max(gaps.c.last_seen).label("last_seen"),
            )
            .where(*conditions)
            .group_by(group, gaps.c.locale)
            .having(occurrences >= f.min_occurrences)
            .order_by(occurrences.desc(), sa.func.min(gaps.c.id))
            .limit(f.limit)
        )
        return [mappers.cluster_from_row(r) for r in rows.mappings()]
