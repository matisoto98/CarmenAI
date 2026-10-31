"""Tablas del ciclo de vida de agentes, tal como las crea 0002_orquestacion.sql."""

from typing import Final

import sqlalchemy as sa

from carmen.adapters.persistence.types import AGENT_STATE, TIMESTAMP, metadata

agent_lifecycle: Final = sa.Table(
    "agent_lifecycle",
    metadata,
    sa.Column("agent_id", sa.Text, primary_key=True),
    sa.Column("state", AGENT_STATE, nullable=False),
    sa.Column("version", sa.Text, nullable=False),
    sa.Column("owner", sa.Text),
    sa.Column("certified_at", TIMESTAMP),
    sa.Column("report_ref", sa.Text),
    sa.Column("updated_at", TIMESTAMP, nullable=False),
)

agent_lifecycle_history: Final = sa.Table(
    "agent_lifecycle_history",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
    sa.Column("seq", sa.BigInteger, sa.Identity(always=True), nullable=False),
    sa.Column("agent_id", sa.Text, nullable=False),
    sa.Column("from_state", AGENT_STATE),
    sa.Column("to_state", AGENT_STATE, nullable=False),
    sa.Column("reason", sa.Text, nullable=False),
    sa.Column("actor", sa.Text, nullable=False),
    sa.Column("at", TIMESTAMP, nullable=False),
)
