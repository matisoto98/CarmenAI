"""ConversationRepository sobre PostgreSQL (7.3, unidad de trabajo 1 de 7.4)."""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError

from carmen.adapters.persistence.conversation import mappers
from carmen.adapters.persistence.conversation.tables import (
    conversations,
    feedback,
    messages,
    tool_calls,
)
from carmen.adapters.persistence.engine import connection
from carmen.application.context import Requester
from carmen.application.ports.repositories import (
    ConversationThread,
    Feedback,
    FeedbackOutcome,
    NewConversation,
    NewMessage,
    NewToolCall,
)
from carmen.domain.errors import ValidationError
from carmen.domain.ids import ConversationId, MessageId
from carmen.domain.time import Instant


class PgConversationRepository:
    """Escribe en la unidad de trabajo en curso; quien la abre decide qué va junto."""

    async def create(self, c: NewConversation) -> ConversationId:
        created = await connection().scalar(
            insert(conversations)
            .values(mappers.conversation_row(c))
            .on_conflict_do_nothing(index_elements=[conversations.c.id])
            .returning(conversations.c.id)
        )
        if created is None:
            msg = f"la conversación {c.conversation_id} ya existe"
            raise ValidationError(msg)
        return c.conversation_id

    async def append_message(self, m: NewMessage, calls: Sequence[NewToolCall]) -> MessageId:
        if any(c.message_id != m.message_id for c in calls):
            msg = "toda llamada pertenece al mensaje con el que se guarda"
            raise ValidationError(msg)
        conn = connection()
        # Bloquear la conversación serializa el cálculo de seq entre mensajes concurrentes.
        locked = await conn.scalar(
            sa.select(conversations.c.id)
            .where(conversations.c.id == str(m.conversation_id))
            .with_for_update()
        )
        if locked is None:
            msg = f"la conversación {m.conversation_id} no existe"
            raise ValidationError(msg)
        seq = await conn.scalar(
            sa.select(sa.func.coalesce(sa.func.max(messages.c.seq), 0) + 1).where(
                messages.c.conversation_id == str(m.conversation_id)
            )
        )
        inserted = await conn.scalar(
            insert(messages)
            .values(mappers.message_row(m, int(seq or 1)))
            .on_conflict_do_nothing(index_elements=[messages.c.id])
            .returning(messages.c.id)
        )
        if inserted is None:
            msg = f"el mensaje {m.message_id} ya existe"
            raise ValidationError(msg)
        if calls:
            await conn.execute(
                sa.insert(tool_calls),
                [mappers.tool_call_row(c, n) for n, c in enumerate(calls, start=1)],
            )
        await self.touch(m.conversation_id, m.created_at)
        return m.message_id

    async def touch(self, cid: ConversationId, at: Instant) -> None:
        await connection().execute(
            sa.update(conversations)
            .where(conversations.c.id == str(cid))
            .values(updated_at=sa.func.greatest(conversations.c.updated_at, at.at))
        )

    async def get_thread(
        self, cid: ConversationId, requester: Requester
    ) -> ConversationThread | None:
        conn = connection()
        found = await conn.execute(
            sa.select(conversations).where(
                conversations.c.id == str(cid),
                conversations.c.user_id == str(requester.principal_id),
            )
        )
        conversation = found.mappings().one_or_none()
        if conversation is None:
            return None
        rows = await conn.execute(
            sa.select(
                messages.c.id,
                messages.c.role,
                messages.c.content,
                messages.c.status,
                messages.c.created_at,
            )
            .where(messages.c.conversation_id == str(cid))
            .order_by(messages.c.seq)
        )
        return mappers.thread_from_rows(conversation, rows.mappings().all())

    async def record_feedback(self, f: Feedback) -> FeedbackOutcome:
        statement = insert(feedback).values(mappers.feedback_row(f))
        excluded = statement.excluded
        upsert = statement.on_conflict_do_update(
            index_elements=[feedback.c.message_id, feedback.c.user_id],
            set_={
                "rating": excluded.rating,
                "comment": excluded.comment,
                "updated_at": excluded.updated_at,
            },
            where=sa.tuple_(feedback.c.rating, feedback.c.comment).is_distinct_from(
                sa.tuple_(excluded.rating, excluded.comment)
            ),
        ).returning(sa.literal_column("xmax = 0", sa.Boolean).label("inserted"))
        try:
            inserted = await connection().scalar(upsert)
        except IntegrityError as error:
            msg = f"no se puede votar el mensaje {f.message_id}: no existe"
            raise ValidationError(msg) from error
        if inserted is None:
            return FeedbackOutcome.UNCHANGED
        return FeedbackOutcome.CREATED if inserted else FeedbackOutcome.UPDATED
