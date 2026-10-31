"""Tabla de temas, tal como la crea 0001_carmen.sql."""

from typing import Final

import sqlalchemy as sa

from carmen.adapters.persistence.types import TEXT_ARRAY, TIMESTAMP, VECTOR, metadata

topics: Final = sa.Table(
    "topics",
    metadata,
    sa.Column("id", sa.Text, primary_key=True),
    sa.Column("label", sa.Text, nullable=False),
    sa.Column("centroid", VECTOR),
    sa.Column("asked", sa.Integer, nullable=False),
    sa.Column("resolved", sa.Integer, nullable=False),
    sa.Column("unresolved", sa.Integer, nullable=False),
    sa.Column("systems", TEXT_ARRAY, nullable=False),
    sa.Column("status", sa.Text, nullable=False),
    sa.Column("first_seen", TIMESTAMP, nullable=False),
    sa.Column("last_seen", TIMESTAMP, nullable=False),
    sa.Column("updated_at", TIMESTAMP, nullable=False),
)
