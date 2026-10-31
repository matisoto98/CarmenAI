"""Tabla de la memoria de planes, tal como la crea 0001_carmen.sql."""

from typing import Final

import sqlalchemy as sa

from carmen.adapters.persistence.types import (
    JSONB,
    LOCALE,
    TEXT_ARRAY,
    TIMESTAMP,
    VECTOR,
    metadata,
)

query_memory: Final = sa.Table(
    "query_memory",
    metadata,
    sa.Column("id", sa.Text, primary_key=True),
    sa.Column("question_norm", sa.Text, nullable=False),
    sa.Column("question", sa.Text, nullable=False),
    sa.Column("embedding", VECTOR, nullable=False),
    sa.Column("plan", JSONB, nullable=False),
    sa.Column("plan_schema_version", sa.Text, nullable=False),
    sa.Column("systems", TEXT_ARRAY, nullable=False),
    sa.Column("locale", LOCALE, nullable=False),
    sa.Column("hits", sa.Integer, nullable=False),
    sa.Column("validated_by", sa.Text),
    sa.Column("active", sa.Boolean, nullable=False),
    sa.Column("created_at", TIMESTAMP, nullable=False),
    sa.Column("updated_at", TIMESTAMP, nullable=False),
)
