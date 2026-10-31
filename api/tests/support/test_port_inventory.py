"""Prompt 5: el inventario de 5.5 coincide con application/ports/, puerto a puerto.

La tabla de abajo ES la de 5.5, con el fichero, el lado y el doble de cada puerto. Si alguien
añade un puerto sin inventariarlo, o lo inventaría sin escribirlo, esta prueba falla.
"""

import ast
import importlib
import inspect
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol

import pytest

import support.fakes as fakes
from carmen.application import errors as port_errors
from carmen.domain import errors as domain_errors

pytestmark = pytest.mark.application

PORTS_DIR: Final = Path(__file__).resolve().parents[2] / "src" / "carmen" / "application" / "ports"


@dataclass(frozen=True)
class Entry:
    module: str
    ports: tuple[str, ...]
    side: str
    doubles: tuple[str, ...]


SUPERVISOR, AGENT, BOTH, EXTERNAL = "supervisor", "agente", "ambos", "agente externo o híbrido"

INVENTORY: Final = (
    Entry("llm", ("LlmPort",), BOTH, ("FakeLlmAdapter",)),
    Entry("embeddings", ("EmbeddingPort",), SUPERVISOR, ("FakeEmbeddingAdapter",)),
    Entry("agents", ("AgentRunnerPort",), SUPERVISOR, ("FakeAgentRunner",)),
    Entry("policy", ("PolicyPort",), SUPERVISOR, ("InMemoryPolicy",)),
    Entry(
        "repositories",
        (
            "ConversationRepository",
            "TurnRepository",
            "MemoryRepository",
            "GapRepository",
            "KnowledgeRepository",
            "BriefRepository",
            "GlossaryRepository",
            "TopicRepository",
            "ApprovalRepository",
            "AgentLifecycleRepository",
        ),
        SUPERVISOR,
        (
            "InMemoryConversationRepository",
            "InMemoryTurnRepository",
            "InMemoryMemoryRepository",
            "InMemoryGapRepository",
            "InMemoryKnowledgeRepository",
            "InMemoryBriefRepository",
            "InMemoryGlossaryRepository",
            "InMemoryTopicRepository",
            "InMemoryApprovalRepository",
            "InMemoryAgentLifecycleRepository",
        ),
    ),
    Entry(
        "system",
        ("Clock", "IdGenerator", "EventSink"),
        BOTH,
        ("FrozenClock", "SeqIdGenerator", "ListEventSink"),
    ),
    Entry("mcp", ("McpClientPort",), AGENT, ("FakeMcpClient",)),
    Entry("identity", ("TokenExchangePort",), AGENT, ("FakeTokenExchange",)),
    Entry("egress", ("EgressPort",), EXTERNAL, ("FakeEgress",)),
    Entry("model_provider", ("ModelProviderPort",), EXTERNAL, ("FakeModelProvider",)),
)


def _protocols(module_name: str) -> dict[str, type]:
    module = importlib.import_module(f"carmen.application.ports.{module_name}")
    return {
        name: obj
        for name, obj in vars(module).items()
        if inspect.isclass(obj)
        and obj.__module__ == module.__name__
        and Protocol in getattr(obj, "__mro__", ())
    }


def _members(protocol: type) -> set[str]:
    return {
        name
        for name, value in vars(protocol).items()
        if not name.startswith("_") and (callable(value) or isinstance(value, property))
    }


def test_the_files_of_ports_are_exactly_the_inventory() -> None:
    files = {p.stem for p in PORTS_DIR.glob("*.py") if p.stem != "__init__"}
    assert files == {e.module for e in INVENTORY}


@pytest.mark.parametrize("entry", INVENTORY, ids=lambda e: e.module)
def test_each_file_declares_exactly_its_ports(entry: Entry) -> None:
    assert sorted(_protocols(entry.module)) == sorted(entry.ports)


@pytest.mark.parametrize("entry", INVENTORY, ids=lambda e: e.module)
def test_each_port_has_its_double_with_every_member(entry: Entry) -> None:
    protocols = _protocols(entry.module)
    for port, double in zip(entry.ports, entry.doubles, strict=True):
        fake = getattr(fakes, double)
        assert _members(protocols[port]) <= set(dir(fake)), f"{double} no cubre {port}"


def test_agent_side_ports_are_forbidden_to_the_supervisor() -> None:
    from architecture.test_layer_rules import AGENT_FORBIDDEN, SUPERVISOR_FORBIDDEN

    agent_side = {f"application.ports.{e.module}" for e in INVENTORY if e.side in (AGENT, EXTERNAL)}
    assert agent_side <= set(SUPERVISOR_FORBIDDEN)
    assert AGENT_FORBIDDEN == ("application.ports.agents",)


def test_the_ports_package_reexports_nothing() -> None:
    """Importar un puerto no arrastra los demás: el supervisor no puede llegar a mcp ni egress."""
    tree = ast.parse((PORTS_DIR / "__init__.py").read_text(encoding="utf-8"))
    assert not [n for n in tree.body if isinstance(n, ast.Import | ast.ImportFrom)]


_RAISES: Final = re.compile(r"Lanza:\s*(.+?)(?:\.\s*$|\.\n|$)", re.DOTALL)


def _declared_errors() -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for entry in INVENTORY:
        for port_name, protocol in _protocols(entry.module).items():
            for member in _members(protocol):
                doc = inspect.getdoc(getattr(protocol, member)) or ""
                for block in _RAISES.findall(doc):
                    for name in re.split(r"[,\s]+", block.strip().rstrip(".")):
                        if name:
                            found.append((f"{port_name}.{member}", name))
    return found


#: Los «Lanza:» de 5.5, 5.13.4 y 5.15.6, método a método, con el sufijo Error de la casa.
EXPECTED_RAISES: Final = {
    "LlmPort.complete_structured": {
        "LlmUnavailableError",
        "LlmTimeoutError",
        "LlmMalformedOutputError",
    },
    "LlmPort.stream_text": {"LlmUnavailableError", "LlmTimeoutError"},
    "EmbeddingPort.embed": {
        "EmbeddingUnavailableError",
        "EmbeddingTimeoutError",
        "EmbeddingDimensionMismatchError",
    },
    "AgentRunnerPort.run": {
        "AgentUnavailableError",
        "AgentTimeoutError",
        "AgentContractViolationError",
    },
    "McpClientPort.list_tools": {"McpUnavailableError", "McpTimeoutError", "McpUnauthorizedError"},
    "McpClientPort.call_tool": {
        "McpUnavailableError",
        "McpTimeoutError",
        "McpForbiddenError",
        "McpToolError",
        "McpContractViolationError",
    },
    "TokenExchangePort.exchange": {
        "IdentityUnavailableError",
        "IdentityRejectedError",
        "IdentityTimeoutError",
    },
    "EgressPort.fetch": {
        "EgressDomainNotAllowedError",
        "EgressClassificationDeniedError",
        "EgressBudgetExceededError",
        "EgressUnavailableError",
    },
    "ModelProviderPort.complete": {
        "ProviderNotBoundError",
        "ClassificationDeniedError",
        "BudgetExceededError",
    },
}


def test_ports_declare_typed_errors_per_method() -> None:
    declared = _declared_errors()
    by_method: dict[str, set[str]] = {}
    for where, name in declared:
        by_method.setdefault(where, set()).add(name)
    assert by_method == EXPECTED_RAISES
    for where, name in declared:
        cls = getattr(port_errors, name, None) or getattr(domain_errors, name, None)
        assert isinstance(cls, type), f"{where} declara {name}, que no existe"
        assert issubclass(cls, domain_errors.CarmenError), f"{where}: {name} no es de Carmen"


def test_port_errors_refine_the_taxonomy_without_new_codes() -> None:
    """Un error de puerto hereda el código de su error de 6.6; no amplía errors.json."""
    taxonomy = {
        cls.code
        for cls in vars(domain_errors).values()
        if isinstance(cls, type) and issubclass(cls, domain_errors.CarmenError)
    }
    refinements = [
        cls
        for cls in vars(port_errors).values()
        if isinstance(cls, type)
        and issubclass(cls, domain_errors.CarmenError)
        and cls.__module__ == port_errors.__name__
    ]
    assert len(refinements) == 20
    for cls in refinements:
        assert "code" not in vars(cls), f"{cls.__name__} no define código propio"
        assert cls.code in taxonomy
        assert not cls.abstract
