"""KnowledgeRepository sobre PostgreSQL con pgvector (7.3)."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert

from carmen.adapters.persistence.engine import connection
from carmen.adapters.persistence.knowledge import mappers
from carmen.adapters.persistence.knowledge.mappers import KnowledgeChunkDraft
from carmen.adapters.persistence.knowledge.tables import knowledge_chunks
from carmen.adapters.persistence.types import cosine_distance, exact_vector_search
from carmen.application.ports.embeddings import Vector
from carmen.application.ports.repositories import KnowledgeChunk
from carmen.application.ports.system import Clock

#: lists del índice ix_kc_vec en 0001_carmen.sql.
KNOWLEDGE_LISTS = 100

__all__ = ["KnowledgeChunkDraft", "PgKnowledgeRepository"]


class PgKnowledgeRepository:
    def __init__(self, clock: Clock) -> None:
        self._clock = clock

    async def search(self, v: Vector, k: int, min_sim: float) -> list[KnowledgeChunk]:
        distance = cosine_distance(knowledge_chunks.c.embedding, v)
        conn = connection()
        await exact_vector_search(conn, KNOWLEDGE_LISTS)
        rows = await conn.execute(
            sa.select(
                knowledge_chunks.c.source,
                knowledge_chunks.c.chunk_ix,
                knowledge_chunks.c.title,
                knowledge_chunks.c.content,
                (1 - distance).label("similarity"),
            )
            .where((1 - distance) >= min_sim)
            .order_by(distance, knowledge_chunks.c.source, knowledge_chunks.c.chunk_ix)
            .limit(k)
        )
        return [mappers.chunk_from_row(r) for r in rows.mappings()]

    async def upsert_chunk(self, c: KnowledgeChunkDraft) -> None:
        """Escritura de la ingesta del corpus; el puerto de la aplicación solo busca."""
        statement = insert(knowledge_chunks).values(mappers.chunk_row(c, self._clock.now()))
        excluded = statement.excluded
        await connection().execute(
            statement.on_conflict_do_update(
                index_elements=[knowledge_chunks.c.source, knowledge_chunks.c.chunk_ix],
                set_={
                    "title": excluded.title,
                    "content": excluded.content,
                    "embedding": excluded.embedding,
                    "updated_at": excluded.updated_at,
                },
            )
        )
