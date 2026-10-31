"""Tablas de la política (7.9.7), tal como las crea 0001_carmen.sql."""

from typing import Final

import sqlalchemy as sa

from carmen.adapters.persistence.types import TEXT_ARRAY, TIMESTAMP, metadata

principals: Final = sa.Table(
    "principals",
    metadata,
    sa.Column("id", sa.Text, primary_key=True),
    sa.Column("directory_ref", sa.Text, nullable=False),
    sa.Column("display_name", sa.Text, nullable=False),
    sa.Column("active", sa.Boolean, nullable=False),
    sa.Column("created_at", TIMESTAMP, nullable=False),
    sa.Column("updated_at", TIMESTAMP, nullable=False),
)

roles: Final = sa.Table(
    "roles",
    metadata,
    sa.Column("id", sa.Text, primary_key=True),
    sa.Column("name", sa.Text, nullable=False),
    sa.Column("platform_actions", TEXT_ARRAY, nullable=False),
    sa.Column("version", sa.Text, nullable=False),
)

role_assignments: Final = sa.Table(
    "role_assignments",
    metadata,
    sa.Column("principal_id", sa.Text, primary_key=True),
    sa.Column("role_id", sa.Text, primary_key=True),
    sa.Column("source", sa.Text, nullable=False),
    sa.Column("granted_at", TIMESTAMP, nullable=False),
)

role_agent_grants: Final = sa.Table(
    "role_agent_grants",
    metadata,
    sa.Column("role_id", sa.Text, primary_key=True),
    sa.Column("agent_id", sa.Text, primary_key=True),
    sa.Column("actions", TEXT_ARRAY, nullable=False),
    sa.Column("scopes", TEXT_ARRAY, nullable=False),
    sa.Column("effect", sa.Text, nullable=False),
    sa.Column("reason", sa.Text),
)

policy_decisions: Final = sa.Table(
    "policy_decisions",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
    sa.Column("turn_id", sa.Text, nullable=False),
    sa.Column("principal_id", sa.Text, nullable=False),
    sa.Column("agent_id", sa.Text),
    sa.Column("action", sa.Text, nullable=False),
    sa.Column("decision", sa.Text, nullable=False),
    sa.Column("reason_code", sa.Text, nullable=False),
    sa.Column("policy_version", sa.Text, nullable=False),
    sa.Column("decided_at", TIMESTAMP, nullable=False),
    # 0002: la ejecución de agente en la que se tomó, su orden y los scopes concedidos
    sa.Column("agent_run_id", sa.Text),
    sa.Column("run_ord", sa.Integer),
    sa.Column("scopes", TEXT_ARRAY, nullable=False),
)
