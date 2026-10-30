"""Prompt 5: cada doble cumple su protocolo.

La comprobación es ESTÁTICA: mypy --strict revisa este fichero (pyproject: files) y falla si un
doble no encaja en su puerto. La prueba en ejecución solo confirma que el módulo se importa y que
cada doble se construye sin infraestructura.
"""

from typing import Final

import pytest

from carmen.application.ports.agents import AgentRunnerPort
from carmen.application.ports.egress import EgressPort
from carmen.application.ports.embeddings import EmbeddingPort
from carmen.application.ports.identity import TokenExchangePort
from carmen.application.ports.llm import LlmPort
from carmen.application.ports.mcp import McpClientPort
from carmen.application.ports.model_provider import ModelProviderPort
from carmen.application.ports.policy import PolicyPort
from carmen.application.ports.repositories import (
    AgentLifecycleRepository,
    ApprovalRepository,
    BriefRepository,
    ConversationRepository,
    GapRepository,
    GlossaryRepository,
    KnowledgeRepository,
    MemoryRepository,
    TopicRepository,
    TurnRepository,
)
from carmen.application.ports.system import Clock, EventSink, IdGenerator
from support.fakes import (
    FakeAgentRunner,
    FakeEgress,
    FakeEmbeddingAdapter,
    FakeLlmAdapter,
    FakeMcpClient,
    FakeModelProvider,
    FakeTokenExchange,
    FrozenClock,
    InMemoryAgentLifecycleRepository,
    InMemoryApprovalRepository,
    InMemoryBriefRepository,
    InMemoryConversationRepository,
    InMemoryGapRepository,
    InMemoryGlossaryRepository,
    InMemoryKnowledgeRepository,
    InMemoryMemoryRepository,
    InMemoryPolicy,
    InMemoryTopicRepository,
    InMemoryTurnRepository,
    ListEventSink,
    SeqIdGenerator,
)

pytestmark = pytest.mark.application

llm: LlmPort = FakeLlmAdapter()
embeddings: EmbeddingPort = FakeEmbeddingAdapter()
agents: AgentRunnerPort = FakeAgentRunner({})
policy: PolicyPort = InMemoryPolicy(version="pol-test")
conversations: ConversationRepository = InMemoryConversationRepository()
turns: TurnRepository = InMemoryTurnRepository()
memory: MemoryRepository = InMemoryMemoryRepository()
gaps: GapRepository = InMemoryGapRepository()
knowledge: KnowledgeRepository = InMemoryKnowledgeRepository()
brief: BriefRepository = InMemoryBriefRepository()
glossary: GlossaryRepository = InMemoryGlossaryRepository()
topics: TopicRepository = InMemoryTopicRepository()
approvals: ApprovalRepository = InMemoryApprovalRepository()
lifecycle: AgentLifecycleRepository = InMemoryAgentLifecycleRepository()
clock: Clock = FrozenClock()
ids: IdGenerator = SeqIdGenerator()
sink: EventSink = ListEventSink()
mcp: McpClientPort = FakeMcpClient(tools={}, responses={})
identity: TokenExchangePort = FakeTokenExchange()
egress: EgressPort = FakeEgress()
provider: ModelProviderPort = FakeModelProvider(bindings={})

DOUBLES: Final[tuple[object, ...]] = (
    llm,
    embeddings,
    agents,
    policy,
    conversations,
    turns,
    memory,
    gaps,
    knowledge,
    brief,
    glossary,
    topics,
    approvals,
    lifecycle,
    clock,
    ids,
    sink,
    mcp,
    identity,
    egress,
    provider,
)


def test_one_double_per_port_built_without_infrastructure() -> None:
    assert len({type(d) for d in DOUBLES}) == len(DOUBLES) == 21
