"""TopicRepository sobre PostgreSQL (7.8.4)."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert

from carmen.adapters.persistence.engine import connection
from carmen.adapters.persistence.topics import mappers
from carmen.adapters.persistence.topics.tables import topics
from carmen.application.ports.repositories import Topic, TopicId, TopicStatus
from carmen.domain.errors import ValidationError
from carmen.domain.time import Instant

_TOPIC_COLUMNS = (
    topics.c.id,
    topics.c.label,
    topics.c.asked,
    topics.c.resolved,
    topics.c.unresolved,
    topics.c.systems,
    topics.c.status,
    topics.c.first_seen,
    topics.c.last_seen,
)


class PgTopicRepository:
    async def upsert(self, t: Topic) -> None:
        statement = insert(topics).values(mappers.topic_values(t))
        excluded = statement.excluded
        await connection().execute(
            statement.on_conflict_do_update(
                index_elements=[topics.c.id],
                set_={
                    name: getattr(excluded, name)
                    for name in (
                        "label",
                        "asked",
                        "resolved",
                        "unresolved",
                        "systems",
                        "status",
                        "first_seen",
                        "last_seen",
                        "updated_at",
                    )
                },
            )
        )

    async def list_by_demand(self, limit: int) -> list[Topic]:
        rows = await connection().execute(
            sa.select(*_TOPIC_COLUMNS).order_by(topics.c.asked.desc(), topics.c.id).limit(limit)
        )
        return [mappers.topic_from_row(r) for r in rows.mappings()]

    async def set_status(self, tid: TopicId, status: TopicStatus, at: Instant) -> Topic:
        result = await connection().execute(
            sa.update(topics)
            .where(topics.c.id == str(tid))
            .values(status=status.value, updated_at=at.at)
            .returning(*_TOPIC_COLUMNS)
        )
        row = result.mappings().one_or_none()
        if row is None:
            msg = f"el tema {tid} no existe"
            raise ValidationError(msg)
        return mappers.topic_from_row(row)
