"""Todas las tablas declaradas, por agregado. La prueba de esquema las compara con la migración."""

from typing import Final

import sqlalchemy as sa

from carmen.adapters.persistence.brief.tables import situation_brief
from carmen.adapters.persistence.conversation.tables import (
    conversations,
    evidence_facts,
    feedback,
    grounding_claims,
    messages,
    tool_calls,
)
from carmen.adapters.persistence.gaps.tables import gaps
from carmen.adapters.persistence.glossary.tables import glossary_history, glossary_terms
from carmen.adapters.persistence.knowledge.tables import knowledge_chunks
from carmen.adapters.persistence.memory.tables import query_memory
from carmen.adapters.persistence.policy.tables import (
    policy_decisions,
    principals,
    role_agent_grants,
    role_assignments,
    roles,
)
from carmen.adapters.persistence.topics.tables import topics

ALL_TABLES: Final[tuple[sa.Table, ...]] = (
    conversations,
    topics,
    messages,
    tool_calls,
    evidence_facts,
    grounding_claims,
    feedback,
    query_memory,
    gaps,
    knowledge_chunks,
    situation_brief,
    glossary_terms,
    glossary_history,
    principals,
    roles,
    role_assignments,
    role_agent_grants,
    policy_decisions,
)
