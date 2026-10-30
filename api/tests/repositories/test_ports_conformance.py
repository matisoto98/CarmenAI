"""Prompt 7: cada adaptador de persistencia implementa el puerto declarado (lo comprueba mypy)."""

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from carmen.adapters.persistence.brief.repository import PgBriefRepository
from carmen.adapters.persistence.conversation.repository import PgConversationRepository
from carmen.adapters.persistence.gaps.repository import PgGapRepository
from carmen.adapters.persistence.glossary.repository import PgGlossaryRepository
from carmen.adapters.persistence.knowledge.repository import PgKnowledgeRepository
from carmen.adapters.persistence.memory.repository import PgMemoryRepository
from carmen.adapters.persistence.policy.repository import PgPolicy
from carmen.adapters.persistence.topics.repository import PgTopicRepository
from carmen.application.ports.policy import PolicyPort
from carmen.application.ports.repositories import (
    BriefRepository,
    ConversationRepository,
    GapRepository,
    GlossaryRepository,
    KnowledgeRepository,
    MemoryRepository,
    TopicRepository,
)
from repositories.pg import Pg
from support.builders import POLICY_VERSION
from support.fakes.system import FrozenClock, SeqIdGenerator

pytestmark = pytest.mark.repositories


def test_persistence_adapters_satisfy_their_ports(pg: Pg) -> None:
    async def build(engine: AsyncEngine) -> list[object]:
        conversations: ConversationRepository = PgConversationRepository()
        memory: MemoryRepository = PgMemoryRepository(SeqIdGenerator(), FrozenClock())
        gaps: GapRepository = PgGapRepository(SeqIdGenerator())
        knowledge: KnowledgeRepository = PgKnowledgeRepository(FrozenClock())
        brief: BriefRepository = PgBriefRepository()
        glossary: GlossaryRepository = PgGlossaryRepository()
        topics: TopicRepository = PgTopicRepository()
        policy: PolicyPort = PgPolicy(engine, version=POLICY_VERSION, clock=FrozenClock())
        return [conversations, memory, gaps, knowledge, brief, glossary, topics, policy]

    assert len(pg.run(lambda db: build(db.engine))) == 8
