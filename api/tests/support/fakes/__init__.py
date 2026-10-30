"""Un doble por puerto del inventario de 5.5. Ninguno importa un adaptador."""

from support.fakes.agents import FakeAgentRunner
from support.fakes.egress import FakeEgress
from support.fakes.embeddings import FakeEmbeddingAdapter
from support.fakes.identity import FakeTokenExchange
from support.fakes.llm import FakeLlmAdapter
from support.fakes.mcp import FakeMcpClient
from support.fakes.model_provider import FakeModelProvider
from support.fakes.policy import InMemoryPolicy
from support.fakes.repositories import (
    InMemoryAgentLifecycleRepository,
    InMemoryApprovalRepository,
    InMemoryBriefRepository,
    InMemoryConversationRepository,
    InMemoryGapRepository,
    InMemoryGlossaryRepository,
    InMemoryKnowledgeRepository,
    InMemoryMemoryRepository,
    InMemoryTopicRepository,
    InMemoryTurnRepository,
)
from support.fakes.system import FrozenClock, ListEventSink, SeqIdGenerator

__all__ = [
    "FakeAgentRunner",
    "FakeEgress",
    "FakeEmbeddingAdapter",
    "FakeLlmAdapter",
    "FakeMcpClient",
    "FakeModelProvider",
    "FakeTokenExchange",
    "FrozenClock",
    "InMemoryAgentLifecycleRepository",
    "InMemoryApprovalRepository",
    "InMemoryBriefRepository",
    "InMemoryConversationRepository",
    "InMemoryGapRepository",
    "InMemoryGlossaryRepository",
    "InMemoryKnowledgeRepository",
    "InMemoryMemoryRepository",
    "InMemoryPolicy",
    "InMemoryTopicRepository",
    "InMemoryTurnRepository",
    "ListEventSink",
    "SeqIdGenerator",
]
