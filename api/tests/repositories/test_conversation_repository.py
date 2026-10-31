"""Prompt 7: agregado conversación (7.3) y unidad de trabajo 1 (7.4). La evidencia, en el turno."""

import pytest

from carmen.adapters.persistence.conversation.repository import PgConversationRepository
from carmen.adapters.persistence.engine import Database, UnitOfWorkError
from carmen.application.ports.repositories import (
    Feedback,
    FeedbackOutcome,
    MessageRole,
    NewConversation,
    NewMessage,
    NewToolCall,
    Rating,
)
from carmen.domain.conversation.turn import TurnStatus
from carmen.domain.errors import ValidationError
from carmen.domain.ids import CallId, ConversationId, MessageId, PrincipalId, StepId
from carmen.domain.locale import Locale
from repositories.pg import Pg
from support.builders import (
    CALL,
    CORRELATION,
    PRINCIPAL,
    VIGIA_SYSTEM,
    at,
    requester,
)

pytestmark = pytest.mark.repositories

CNV = ConversationId("cnv_0001")
OTHER = PrincipalId("usr_b22c")
CALL_1 = CALL
CALL_2 = CallId("cal_s2r1")


def conversation(cid: ConversationId = CNV) -> NewConversation:
    return NewConversation(cid, PRINCIPAL, Locale.ES, at(0), title="Monitores")


def message(n: int, role: MessageRole = MessageRole.ASSISTANT, seconds: float = 0) -> NewMessage:
    return NewMessage(
        message_id=MessageId(f"msg_{n:04d}"),
        conversation_id=CNV,
        role=role,
        content=f"respuesta {n}",
        status=TurnStatus.COMPLETED,
        correlation_id=CORRELATION,
        created_at=at(seconds or n),
        locale=Locale.ES,
    )


def tool_call(mid: MessageId, call_id: CallId = CALL_1, *, ok: bool = True) -> NewToolCall:
    return NewToolCall(
        call_id=call_id,
        message_id=mid,
        step_id=StepId("s1"),
        system_id=VIGIA_SYSTEM,
        tool_name="query_metric",
        arguments={"metric": "monitores_ko", "window": {"hours": 24}},
        ok=ok,
        created_at=at(1),
        error_code=None if ok else "timeout",
        facts_count=1 if ok else 0,
        ms=180,
    )


def test_the_thread_lists_messages_in_order_and_touches_the_conversation(pg: Pg) -> None:
    repo = PgConversationRepository()

    async def scenario(db: Database) -> None:
        async with db.unit_of_work():
            await repo.create(conversation())
            await repo.append_message(message(1, MessageRole.USER), [])
            await repo.append_message(message(2), [])
            await repo.touch(CNV, at(-5))  # nunca retrocede
        async with db.unit_of_work():
            thread = await repo.get_thread(CNV, requester())
            assert thread is not None
            assert thread.title == "Monitores"
            assert [(m.message_id, m.role) for m in thread.messages] == [
                (MessageId("msg_0001"), MessageRole.USER),
                (MessageId("msg_0002"), MessageRole.ASSISTANT),
            ]
            assert thread.messages[1].created_at == at(2)

    pg.run(scenario)
    rows = pg.fetch("SELECT seq FROM carmen.messages ORDER BY seq")
    assert [r["seq"] for r in rows] == [1, 2]
    updated = pg.fetch("SELECT updated_at FROM carmen.conversations")[0]["updated_at"]
    assert updated == at(2).at


def test_another_persons_thread_looks_like_a_missing_one(pg: Pg) -> None:
    repo = PgConversationRepository()

    async def scenario(db: Database) -> None:
        async with db.unit_of_work():
            await repo.create(conversation())
        async with db.unit_of_work():
            assert await repo.get_thread(CNV, requester(OTHER)) is None
            assert await repo.get_thread(ConversationId("cnv_9999"), requester()) is None

    pg.run(scenario)


def test_duplicates_and_foreign_calls_are_validation_errors(pg: Pg) -> None:
    repo = PgConversationRepository()
    msg = message(1)

    async def scenario(db: Database) -> None:
        async with db.unit_of_work():
            await repo.create(conversation())
            await repo.append_message(msg, [])
        with pytest.raises(ValidationError, match="ya existe"):
            async with db.unit_of_work():
                await repo.create(conversation())
        with pytest.raises(ValidationError, match="ya existe"):
            async with db.unit_of_work():
                await repo.append_message(msg, [])
        with pytest.raises(ValidationError, match="pertenece"):
            async with db.unit_of_work():
                await repo.append_message(message(2), [tool_call(msg.message_id)])
        with pytest.raises(ValidationError, match="no existe"):
            async with db.unit_of_work():
                await repo.append_message(
                    NewMessage(
                        MessageId("msg_0003"),
                        ConversationId("cnv_9999"),
                        MessageRole.USER,
                        "hola",
                        TurnStatus.COMPLETED,
                        CORRELATION,
                        at(3),
                    ),
                    [],
                )

    pg.run(scenario)
    assert len(pg.fetch("SELECT id FROM carmen.messages")) == 1


def test_voting_twice_updates_instead_of_duplicating(pg: Pg) -> None:
    repo = PgConversationRepository()
    mid = MessageId("msg_0001")

    async def scenario(db: Database) -> list[FeedbackOutcome]:
        async with db.unit_of_work():
            await repo.create(conversation())
            await repo.append_message(message(1), [])
        outcomes = []
        for vote in (
            Feedback(mid, PRINCIPAL, Rating.UP, at(10)),
            Feedback(mid, PRINCIPAL, Rating.UP, at(11)),
            Feedback(mid, PRINCIPAL, Rating.DOWN, at(12), comment="cifra antigua"),
            Feedback(mid, OTHER, Rating.UP, at(13)),
        ):
            async with db.unit_of_work():
                outcomes.append(await repo.record_feedback(vote))
        return outcomes

    assert pg.run(scenario) == [
        FeedbackOutcome.CREATED,
        FeedbackOutcome.UNCHANGED,
        FeedbackOutcome.UPDATED,
        FeedbackOutcome.CREATED,
    ]
    rows = pg.fetch(
        "SELECT user_id, rating, comment, created_at, updated_at FROM carmen.feedback"
        " ORDER BY user_id"
    )
    assert [(r["user_id"], r["rating"], r["comment"]) for r in rows] == [
        ("usr_a91f", -1, "cifra antigua"),
        ("usr_b22c", 1, None),
    ]
    assert (rows[0]["created_at"], rows[0]["updated_at"]) == (at(10).at, at(12).at)


def test_feedback_on_a_missing_message_is_a_validation_error(pg: Pg) -> None:
    repo = PgConversationRepository()

    async def scenario(db: Database) -> None:
        with pytest.raises(ValidationError, match="msg_0404"):
            async with db.unit_of_work():
                await repo.record_feedback(
                    Feedback(MessageId("msg_0404"), PRINCIPAL, Rating.UP, at())
                )

    pg.run(scenario)


def test_a_repository_never_opens_its_own_transaction(pg: Pg) -> None:
    repo = PgConversationRepository()

    async def scenario(db: Database) -> None:
        with pytest.raises(UnitOfWorkError):
            await repo.create(conversation())

    pg.run(scenario)
    assert pg.fetch("SELECT id FROM carmen.conversations") == []
