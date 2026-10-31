"""MemoryRepository sobre PostgreSQL con pgvector (7.3, unidad de trabajo 3 de 7.4)."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert

from carmen.adapters.persistence.engine import connection
from carmen.adapters.persistence.memory import mappers
from carmen.adapters.persistence.memory.tables import query_memory
from carmen.adapters.persistence.types import as_text, cosine_distance, exact_vector_search
from carmen.application.ports.embeddings import Vector
from carmen.application.ports.repositories import MemoryExample, MemoryExampleDraft, MemoryId
from carmen.application.ports.system import Clock, IdGenerator
from carmen.domain.errors import ValidationError
from carmen.domain.ids import PrincipalId
from carmen.domain.plan.models import SCHEMA_VERSION

#: lists del índice ix_mem_vec en 0001_carmen.sql.
MEMORY_LISTS = 100


class PgMemoryRepository:
    def __init__(self, ids: IdGenerator, clock: Clock) -> None:
        self._ids = ids
        self._clock = clock

    async def similar_plans(self, v: Vector, k: int, min_sim: float) -> list[MemoryExample]:
        distance = cosine_distance(query_memory.c.embedding, v)
        similarity = (1 - distance).label("similarity")
        conn = connection()
        await exact_vector_search(conn, MEMORY_LISTS)
        rows = await conn.execute(
            sa.select(
                query_memory.c.id,
                query_memory.c.question,
                as_text(query_memory.c.plan).label("plan"),
                query_memory.c.locale,
                query_memory.c.hits,
                similarity,
            )
            .where(
                query_memory.c.active,
                # Un plan de otra versión del esquema no se reutiliza: se replanifica.
                query_memory.c.plan_schema_version == SCHEMA_VERSION,
                (1 - distance) >= min_sim,
            )
            .order_by(distance, query_memory.c.id)
            .limit(k)
        )
        return [mappers.example_from_row(r) for r in rows.mappings()]

    async def upsert_example(self, e: MemoryExampleDraft) -> MemoryId:
        candidate = MemoryId(f"mem_{self._ids.new_id()}")
        statement = insert(query_memory).values(
            mappers.example_row(candidate, e, self._clock.now())
        )
        excluded = statement.excluded
        upsert = statement.on_conflict_do_update(
            index_elements=[query_memory.c.question_norm, query_memory.c.locale],
            set_={
                "hits": query_memory.c.hits + 1,
                "question": excluded.question,
                "embedding": excluded.embedding,
                "plan": excluded.plan,
                "plan_schema_version": excluded.plan_schema_version,
                "systems": excluded.systems,
                "validated_by": sa.func.coalesce(
                    excluded.validated_by, query_memory.c.validated_by
                ),
                "active": True,
                "updated_at": excluded.updated_at,
            },
        ).returning(query_memory.c.id)
        return MemoryId((await connection().execute(upsert)).scalar_one())

    async def deactivate(self, mid: MemoryId, by: PrincipalId) -> None:
        """Se retira de la reutilización; la fila se conserva. Quién lo hizo lo audita el caso
        de uso con su evento.
        """
        result = await connection().execute(
            sa.update(query_memory)
            .where(query_memory.c.id == str(mid))
            .values(active=False, updated_at=self._clock.now().at)
        )
        if result.rowcount == 0:
            msg = f"el ejemplo {mid} no existe"
            raise ValidationError(msg)
