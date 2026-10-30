"""Tabla de lagunas, tal como la crea 0001_carmen.sql."""

from typing import Final

import sqlalchemy as sa

from carmen.adapters.persistence.types import LOCALE, TIMESTAMP, VECTOR, metadata

gaps: Final = sa.Table(
    "gaps",
    metadata,
    sa.Column("id", sa.Text, primary_key=True),
    sa.Column("question_norm", sa.Text, nullable=False),
    sa.Column("question", sa.Text, nullable=False),
    sa.Column("embedding", VECTOR, nullable=False),
    sa.Column("locale", LOCALE, nullable=False),
    sa.Column("reason", sa.Text, nullable=False),
    sa.Column("cluster_id", sa.Uuid),
    sa.Column("cluster_name", sa.Text),
    sa.Column("occurrences", sa.Integer, nullable=False),
    sa.Column("status", sa.Text, nullable=False),
    sa.Column("first_seen", TIMESTAMP, nullable=False),
    sa.Column("last_seen", TIMESTAMP, nullable=False),
)
