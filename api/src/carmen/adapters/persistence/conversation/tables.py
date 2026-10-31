"""Tablas del agregado conversación, tal como las dejan 0001_carmen.sql y 0002_orquestacion.sql.

El mensaje del asistente ES el turno (7.3.1): las columnas de 0002 en messages son las suyas.
"""

from typing import Final

import sqlalchemy as sa

from carmen.adapters.persistence.types import (
    JSONB,
    LOCALE,
    MONEY,
    MSG_STATUS,
    RESPONSE_MODE,
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
    # 0002: el turno
    sa.Column("turn_id", sa.Text),
    sa.Column("response_mode", RESPONSE_MODE),
    sa.Column("policy_version", sa.Text),
    sa.Column("delegation_plan", JSONB),
    sa.Column("agents_used", TEXT_ARRAY, nullable=False),
    sa.Column("missing_agents", TEXT_ARRAY, nullable=False),
    sa.Column("redelegations", sa.Integer, nullable=False),
    sa.Column("cost_eur", MONEY, nullable=False),
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
    # 0002: la ejecución de agente a la que pertenece, y su orden dentro de ella
    sa.Column("agent_run_id", sa.Text),
    sa.Column("run_ord", sa.Integer),
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
    # 0002: lo necesario para reconstruir el EvidenceFact del turno
    sa.Column("ord", sa.Integer),
    sa.Column("system_id", sa.Text),
    sa.Column("value_kind", sa.Text),
    sa.Column("metric", sa.Text),
    sa.Column("entity_name", sa.Text),
    sa.Column("provenance_tool", sa.Text),
    sa.Column("provenance_catalog_version", sa.Text),
    sa.Column("provenance_generated_at", TIMESTAMP),
)

evidence_passages: Final = sa.Table(
    "evidence_passages",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
    sa.Column("message_id", sa.Text, nullable=False),
    sa.Column("tool_call_id", sa.Uuid, nullable=False),
    sa.Column("ord", sa.Integer, nullable=False),
    sa.Column("passage_key", sa.Text, nullable=False),
    sa.Column("system_id", sa.Text, nullable=False),
    sa.Column("document_id", sa.Text, nullable=False),
    sa.Column("title", sa.Text, nullable=False),
    sa.Column("body", sa.Text, nullable=False),
    sa.Column("kind", sa.Text, nullable=False),
    sa.Column("relevance", sa.Float, nullable=False),
    sa.Column("section", sa.Text),
    sa.Column("anchor", sa.Text),
    sa.Column("doc_version", sa.Text),
    sa.Column("updated_at", TIMESTAMP),
    sa.Column("url", sa.Text),
)

evidence_media: Final = sa.Table(
    "evidence_media",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
    sa.Column("message_id", sa.Text, nullable=False),
    sa.Column("tool_call_id", sa.Uuid, nullable=False),
    sa.Column("ord", sa.Integer, nullable=False),
    sa.Column("media_key", sa.Text, nullable=False),
    sa.Column("system_id", sa.Text, nullable=False),
    sa.Column("document_id", sa.Text, nullable=False),
    sa.Column("mime", sa.Text, nullable=False),
    sa.Column("caption", sa.Text, nullable=False),
    sa.Column("uri", sa.Text, nullable=False),
    sa.Column("bytes", sa.BigInteger),
    sa.Column("anchor", sa.Text),
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
    # 0002: identidad y tramo de la afirmación, y su orden en el resultado de anclaje
    sa.Column("ord", sa.Integer),
    sa.Column("claim_key", sa.Text),
    sa.Column("span_start", sa.Integer),
    sa.Column("span_end", sa.Integer),
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
