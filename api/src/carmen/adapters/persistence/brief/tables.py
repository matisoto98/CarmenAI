"""Tabla del brief de situación (fila única), tal como la crea 0001_carmen.sql."""

from typing import Final

import sqlalchemy as sa

from carmen.adapters.persistence.types import JSONB, TIMESTAMP, metadata

situation_brief: Final = sa.Table(
    "situation_brief",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("payload", JSONB, nullable=False),
    sa.Column("generated_at", TIMESTAMP, nullable=False),
)
