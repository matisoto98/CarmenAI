"""Tabla del corpus organizativo, tal como la crea 0001_carmen.sql."""

from typing import Final

import sqlalchemy as sa

from carmen.adapters.persistence.types import TIMESTAMP, VECTOR, metadata

knowledge_chunks: Final = sa.Table(
    "knowledge_chunks",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
    sa.Column("source", sa.Text, nullable=False),
    sa.Column("title", sa.Text, nullable=False),
    sa.Column("chunk_ix", sa.Integer, nullable=False),
    sa.Column("content", sa.Text, nullable=False),
    sa.Column("embedding", VECTOR, nullable=False),
    sa.Column("created_at", TIMESTAMP, nullable=False),
    sa.Column("updated_at", TIMESTAMP, nullable=False),
)
