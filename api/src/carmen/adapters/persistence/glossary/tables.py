"""Tablas del glosario y su historial, tal como las crea 0001_carmen.sql."""

from typing import Final

import sqlalchemy as sa

from carmen.adapters.persistence.types import JSONB, TEXT_ARRAY, TIMESTAMP, metadata

glossary_terms: Final = sa.Table(
    "glossary_terms",
    metadata,
    sa.Column("term", sa.Text, primary_key=True),
    sa.Column("display", sa.Text, nullable=False),
    sa.Column("definition", sa.Text, nullable=False),
    sa.Column("aliases", TEXT_ARRAY, nullable=False),
    sa.Column("canonical", sa.Boolean, nullable=False),
    sa.Column("active", sa.Boolean, nullable=False),
    sa.Column("source", sa.Text, nullable=False),
    sa.Column("created_by", sa.Text, nullable=False),
    sa.Column("created_at", TIMESTAMP, nullable=False),
    sa.Column("updated_by", sa.Text, nullable=False),
    sa.Column("updated_at", TIMESTAMP, nullable=False),
)

glossary_history: Final = sa.Table(
    "glossary_history",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
    sa.Column("seq", sa.BigInteger, sa.Identity(always=True), nullable=False),
    sa.Column("term", sa.Text, nullable=False),
    sa.Column("action", sa.Text, nullable=False),
    sa.Column("before", JSONB),
    sa.Column("after", JSONB),
    sa.Column("actor", sa.Text, nullable=False),
    sa.Column("at", TIMESTAMP, nullable=False),
)
