"""Tablas del agregado conversación, tal como las crea 0001_carmen.sql."""

from typing import Final

import sqlalchemy as sa

from carmen.adapters.persistence.types import (
    JSONB,
    LOCALE,
    MSG_STATUS,
    ROLE,
    TEXT_ARRAY,
    TIMESTAMP,
    metadata,
)

conversations: Final = sa.Table(
    "conversations",
    metadata,
    sa.Column("id", sa.Text, primary_key=True),
    sa.Column("user_id", sa.Text, nullable=False),
    sa.Column("locale", LOCALE, nullable=False),
    sa.Column("channel", sa.Text, nullable=False),
    sa.Column("title", sa.Text),
    sa.Column("created_at", TIMESTAMP, nullable=False),
    sa.Column("updated_at", TIMESTAMP, nullable=False),
)

messages: Final = sa.Table(
    "messages",
    metadata,
    sa.Column("id", sa.Text, primary_key=True),
    sa.Column("conversation_id", sa.Text, nullable=False),
    sa.Column("seq", sa.Integer, nullable=False),
    sa.Column("role", sa.Text, nullable=False),
    sa.Column("content", sa.Text, nullable=False),
    sa.Column("locale", LOCALE),
    sa.Column("intent", sa.Text),
    sa.Column("status", MSG_STATUS, nullable=False),
    sa.Column("partial", sa.Boolean, nullable=False),
    sa.Column("missing_systems", TEXT_ARRAY, nullable=False),
    sa.Column("observed_role", ROLE),
    sa.Column("authz_denied", sa.Integer, nullable=False),
    sa.Column("plan_id", sa.Text),
    sa.Column("plan_schema_version", sa.Text),
    sa.Column("round", sa.Integer, nullable=False),
    sa.Column("repairs", sa.Integer, nullable=False),
    sa.Column("model_id", sa.Text),
    sa.Column("model_revision", sa.Text),
    sa.Column("prompt_hash", sa.Text),
    sa.Column("catalog_versions", JSONB, nullable=False),
    sa.Column("contract_version", sa.Text),
    sa.Column("grounding_ok", sa.Boolean),
    sa.Column("grounding_unsupported", sa.Integer, nullable=False),
    sa.Column("tokens_in", sa.Integer),
    sa.Column("tokens_out", sa.Integer),
    sa.Column("latency_ms", sa.Integer),
    sa.Column("correlation_id", sa.Text, nullable=False),
    sa.Column("created_at", TIMESTAMP, nullable=False),
    sa.Column("topic_id", sa.Text),
)

tool_calls: Final = sa.Table(
    "tool_calls",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
    sa.Column("message_id", sa.Text, nullable=False),
    sa.Column("seq", sa.Integer, nullable=False),
    sa.Column("step_id", sa.Text, nullable=False),
    sa.Column("call_id", sa.Text, nullable=False),
    sa.Column("system_id", sa.Text, nullable=False),
    sa.Column("tool_name", sa.Text, nullable=False),
    sa.Column("arguments", JSONB, nullable=False),
    sa.Column("ok", sa.Boolean, nullable=False),
    sa.Column("error_code", sa.Text),
    sa.Column("facts_count", sa.Integer, nullable=False),
    sa.Column("partial", sa.Boolean, nullable=False),
    sa.Column("repaired", sa.Boolean, nullable=False),
    sa.Column("ms", sa.Integer),
    sa.Column("created_at", TIMESTAMP, nullable=False),
)

evidence_facts: Final = sa.Table(
    "evidence_facts",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
    sa.Column("message_id", sa.Text, nullable=False),
    sa.Column("tool_call_id", sa.Uuid, nullable=False),
    sa.Column("fact_key", sa.Text, nullable=False),
    sa.Column("label", sa.Text, nullable=False),
    sa.Column("value_num", sa.Numeric(asdecimal=True)),
    sa.Column("value_text", sa.Text),
    sa.Column("unit", sa.Text),
    sa.Column("entity_type", sa.Text),
    sa.Column("entity_id", sa.Text),
    sa.Column("dimensions", JSONB, nullable=False),
    sa.Column("period", JSONB),
)

grounding_claims: Final = sa.Table(
    "grounding_claims",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
    sa.Column("message_id", sa.Text, nullable=False),
    sa.Column("raw_value", sa.Text, nullable=False),
    sa.Column("normalized", sa.Numeric(asdecimal=True)),
    sa.Column("verdict", sa.Text, nullable=False),
    sa.Column("fact_id", sa.Uuid),
    sa.Column("reason", sa.Text),
)

feedback: Final = sa.Table(
    "feedback",
    metadata,
    sa.Column("message_id", sa.Text, primary_key=True),
    sa.Column("user_id", sa.Text, primary_key=True),
    sa.Column("rating", sa.SmallInteger, nullable=False),
    sa.Column("comment", sa.Text),
    sa.Column("created_at", TIMESTAMP, nullable=False),
    sa.Column("updated_at", TIMESTAMP, nullable=False),
)
