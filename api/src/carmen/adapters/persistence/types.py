"""Tipos compartidos de persistencia: vector, JSON, enumeraciones del dominio e instantes (7.2).

Las enumeraciones SQL se construyen desde las del dominio, y una prueba comprueba que la migración
declara exactamente los mismos valores (7.1, «Enumeraciones compartidas»).
"""

import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from typing import Final

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncConnection
from sqlalchemy.types import UserDefinedType

from carmen.application.errors import EmbeddingDimensionMismatchError
from carmen.application.jsontypes import JsonValue
from carmen.application.ports.embeddings import Vector
from carmen.domain.agents.card import AgentLifecycleState
from carmen.domain.approval.models import ApprovalStatus
from carmen.domain.conversation.turn import TurnStatus
from carmen.domain.delegation.models import AgentResultStatus
from carmen.domain.errors import ValidationError
from carmen.domain.locale import Locale
from carmen.domain.orchestration.mode import ResponseMode
from carmen.domain.role import Role
from carmen.domain.time import Instant

#: Dimensión FIJA del embedding (ADR-014). Cambiarla exige migración y reindexado.
EMBEDDING_DIM: Final = 1024

metadata: Final = sa.MetaData(schema="carmen")

MSG_STATUS: Final = postgresql.ENUM(
    *(s.value for s in TurnStatus), name="msg_status", schema="carmen", create_type=False
)
LOCALE: Final = postgresql.ENUM(
    *(loc.value for loc in Locale), name="locale", schema="carmen", create_type=False
)
ROLE: Final = postgresql.ENUM(
    *(r.value for r in Role), name="role", schema="carmen", create_type=False
)
# 0002_orquestacion.sql
RESPONSE_MODE: Final = postgresql.ENUM(
    *(m.value for m in ResponseMode), name="response_mode", schema="carmen", create_type=False
)
AGENT_STATE: Final = postgresql.ENUM(
    *(s.value for s in AgentLifecycleState),
    name="agent_state",
    schema="carmen",
    create_type=False,
)
AGENT_RESULT_STATUS: Final = postgresql.ENUM(
    *(s.value for s in AgentResultStatus),
    name="agent_result_status",
    schema="carmen",
    create_type=False,
)
APPROVAL_STATUS: Final = postgresql.ENUM(
    *(s.value for s in ApprovalStatus), name="approval_status", schema="carmen", create_type=False
)
MONEY: Final = sa.Numeric(12, 4, asdecimal=True)
TEXT_ARRAY: Final = postgresql.ARRAY(sa.Text)
TIMESTAMP: Final = sa.DateTime(timezone=True)


class PgVector(UserDefinedType[str]):
    """vector(n) de pgvector. Viaja como texto y se convierte en el servidor."""

    cache_ok = True

    def __init__(self, dim: int = EMBEDDING_DIM) -> None:
        self.dim = dim

    def get_col_spec(self, **kw: object) -> str:
        return f"vector({self.dim})"


class PgJsonb(UserDefinedType[str]):
    """jsonb que viaja como texto ya serializado por el mapeador (dumps) y se lee como texto
    (as_text + loads): así ningún Decimal se convierte en float por el camino.
    """

    cache_ok = True

    def get_col_spec(self, **kw: object) -> str:
        return "jsonb"


VECTOR: Final = PgVector()
JSONB: Final = PgJsonb()


def vector_value(v: Vector) -> sa.ColumnElement[str]:
    """Un vector como expresión SQL. Otra dimensión que la fija se rechaza antes de escribir."""
    if len(v) != EMBEDDING_DIM:
        msg = f"el vector tiene dimensión {len(v)}; la de Carmen es {EMBEDDING_DIM}"
        raise EmbeddingDimensionMismatchError(msg)
    literal = "[" + ",".join(repr(float(x)) for x in v) + "]"
    return sa.cast(sa.literal(literal, sa.Text), VECTOR)


def cosine_distance(column: sa.ColumnElement[str], v: Vector) -> sa.ColumnElement[float]:
    """Distancia coseno de pgvector (<=>). La similitud es 1 menos la distancia."""
    return column.op("<=>", return_type=sa.Float)(vector_value(v))


async def exact_vector_search(conn: AsyncConnection, lists: int) -> None:
    """Recorre todas las listas del índice ivfflat en esta transacción: la búsqueda es exacta.

    Con pocas filas por lista, sondear solo una deja fuera vecinos que superan el umbral.
    """
    await conn.execute(sa.text(f"SET LOCAL ivfflat.probes = {int(lists)}"))


def as_text(column: sa.ColumnElement[str]) -> sa.ColumnElement[str]:
    """Lee una columna jsonb o vector como texto, para que la convierta el mapeador."""
    return sa.cast(column, sa.Text)


def dumps(value: JsonValue) -> str:
    """JSON estable: claves ordenadas, sin espacios y con caracteres sin escapar."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def loads(text: str) -> JsonValue:
    """Los números con decimales vuelven como Decimal, nunca como float."""
    return json.loads(text, parse_float=Decimal)  # type: ignore[no-any-return]


def instant(value: datetime) -> Instant:
    return Instant(value)


def as_mapping(value: JsonValue) -> Mapping[str, JsonValue]:
    if not isinstance(value, Mapping):
        msg = f"se esperaba un objeto JSON y llegó {type(value).__name__}"
        raise ValidationError(msg)
    return value


def as_sequence(value: JsonValue) -> Sequence[JsonValue]:
    if isinstance(value, str) or not isinstance(value, Sequence):
        msg = f"se esperaba una lista JSON y llegó {type(value).__name__}"
        raise ValidationError(msg)
    return value
