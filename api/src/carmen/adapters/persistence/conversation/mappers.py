"""Conversación: tabla ⇄ dominio, sin filas de SQLAlchemy hacia arriba (7.2)."""

from collections.abc import Sequence
from decimal import Decimal
from uuid import UUID

from sqlalchemy import RowMapping

from carmen.adapters.persistence.types import dumps, instant
from carmen.application.ports.repositories import (
    ConversationThread,
    Feedback,
    MessageRole,
    NewConversation,
    NewMessage,
    NewToolCall,
    ThreadMessage,
)
from carmen.domain.conversation.turn import TurnStatus
from carmen.domain.evidence.models import EvidenceFact, FactValue, PeriodInterpreted
from carmen.domain.ids import ConversationId, MessageId, PrincipalId
from carmen.domain.locale import Locale

type Values = dict[str, object]


def conversation_row(c: NewConversation) -> Values:
    return {
        "id": str(c.conversation_id),
        "user_id": str(c.owner),
        "locale": c.locale.value,
        "channel": c.channel,
        "title": c.title,
        "created_at": c.created_at.at,
        "updated_at": c.created_at.at,
    }


def message_row(m: NewMessage, seq: int) -> Values:
    return {
        "id": str(m.message_id),
        "conversation_id": str(m.conversation_id),
        "seq": seq,
        "role": m.role.value,
        "content": m.content,
        "locale": None if m.locale is None else m.locale.value,
        "status": m.status.value,
        "correlation_id": str(m.correlation_id),
        "created_at": m.created_at.at,
    }


def tool_call_row(c: NewToolCall, seq: int) -> Values:
    return {
        "message_id": str(c.message_id),
        "seq": seq,
        "step_id": str(c.step_id),
        "call_id": str(c.call_id),
        "system_id": str(c.system_id),
        "tool_name": c.tool_name,
        "arguments": dumps(c.arguments),
        "ok": c.ok,
        "error_code": c.error_code,
        "facts_count": c.facts_count,
        "partial": c.partial,
        "repaired": c.repaired,
        "ms": c.ms,
        "created_at": c.created_at.at,
    }


def _split_value(value: FactValue) -> tuple[Decimal | None, str | None]:
    """Un número va a value_num, exacto; un texto o un booleano, a value_text."""
    if isinstance(value, bool):
        return None, "true" if value else "false"
    if isinstance(value, Decimal | int):
        return Decimal(value), None
    return None, value


def _period(p: PeriodInterpreted | None) -> str | None:
    if p is None:
        return None
    return dumps(
        {
            "expression": p.expression,
            "start": p.start.isoformat(),
            "end": p.end.isoformat(),
            "text": p.text,
        }
    )


def evidence_row(message_id: MessageId, tool_call_id: UUID, f: EvidenceFact) -> Values:
    value_num, value_text = _split_value(f.value)
    return {
        "message_id": str(message_id),
        "tool_call_id": tool_call_id,
        "fact_key": str(f.fact_id),
        "label": f.label,
        "value_num": value_num,
        "value_text": value_text,
        "unit": None if f.unit is None else f.unit.value,
        "entity_type": None if f.entity is None else f.entity.type,
        "entity_id": None if f.entity is None else f.entity.id,
        "dimensions": dumps(dict(f.dimensions)),
        "period": _period(f.period),
    }


def feedback_row(f: Feedback) -> Values:
    return {
        "message_id": str(f.message_id),
        "user_id": str(f.principal_id),
        "rating": int(f.rating),
        "comment": f.comment,
        "created_at": f.at.at,
        "updated_at": f.at.at,
    }


def thread_from_rows(c: RowMapping, rows: Sequence[RowMapping]) -> ConversationThread:
    return ConversationThread(
        conversation_id=ConversationId(c["id"]),
        owner=PrincipalId(c["user_id"]),
        locale=Locale(c["locale"]),
        title=c["title"],
        messages=tuple(
            ThreadMessage(
                message_id=MessageId(r["id"]),
                role=MessageRole(r["role"]),
                content=r["content"],
                status=TurnStatus(r["status"]),
                created_at=instant(r["created_at"]),
            )
            for r in rows
        ),
    )
