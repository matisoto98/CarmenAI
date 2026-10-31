"""Tabla de aprobaciones, tal como la crea 0002_orquestacion.sql."""

from typing import Final

import sqlalchemy as sa

from carmen.adapters.persistence.types import APPROVAL_STATUS, JSONB, ROLE, TIMESTAMP, metadata

approvals: Final = sa.Table(
    "approvals",
    metadata,
    sa.Column("id", sa.Text, primary_key=True),
    sa.Column("turn_id", sa.Text, nullable=False),
    sa.Column("agent_id", sa.Text, nullable=False),
    sa.Column("agent_run_id", sa.Text),
    sa.Column("action", sa.Text, nullable=False),
    sa.Column("impact", sa.Text, nullable=False),
    sa.Column("summary", sa.Text, nullable=False),
    sa.Column("evidence_refs", JSONB, nullable=False),
    sa.Column("required_role", ROLE, nullable=False),
    sa.Column("status", APPROVAL_STATUS, nullable=False),
    sa.Column("decided_by", sa.Text),
    sa.Column("decided_at", TIMESTAMP),
    sa.Column("expires_at", TIMESTAMP, nullable=False),
    sa.Column("created_at", TIMESTAMP, nullable=False),
)
