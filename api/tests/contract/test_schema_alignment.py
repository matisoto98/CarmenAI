"""Prompt 4: los esquemas de contracts/ son la fuente; el dominio se verifica contra ellos.

Sin generación de código (ADR-021).

Tres comprobaciones, sin generación de código:
  1. Cada esquema valida sus ejemplos positivos y rechaza los negativos (6.2.3, 6.12.3).
  2. Cada objeto del esquema coincide campo a campo con su tipo del dominio: mismos nombres y
     mismos obligatorios. Las diferencias admitidas están escritas aquí, una a una.
  3. Los enumerados, los patrones de identificador y los códigos de error coinciden.

Los contratos que todavía no tienen tipo en el dominio (sobre MCP, servidores, SSE, registros)
quedan fijados por tablas de campos: añadir un campo obligatorio al esquema rompe esta prueba.
"""

import dataclasses
import json
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from functools import cache
from pathlib import Path
from typing import Final, cast, get_args

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012, Schema

from carmen.domain import errors as domain_errors
from carmen.domain import ids
from carmen.domain.agents.card import (
    AgentBudgets,
    AgentCard,
    AgentLifecycleState,
    AgentSlo,
    Connectivity,
    Visibility,
)
from carmen.domain.approval.models import ApprovalRecord, ApprovalStatus, Impact
from carmen.domain.conversation.turn import ConversationTurn, TokenUsage, TurnStatus
from carmen.domain.delegation import models as delegation
from carmen.domain.delegation.models import (
    AgentDomain,
    AgentResult,
    AgentResultStatus,
    AgentRun,
    AgentTask,
    AgentWarning,
    Budgets,
    Composition,
    CompositionKind,
    DelegationPlan,
    Expects,
    ExternalCallTrace,
    NeedDelegation,
    NeedDelegationReason,
    TaskBudgets,
    ToolCallTrace,
)
from carmen.domain.egress.models import DataClass, Purpose
from carmen.domain.evidence.grounding import GroundingClaim, GroundingResult, TextSpan, Verdict
from carmen.domain.evidence.models import (
    EntityRef,
    EvidenceFact,
    EvidenceMedia,
    EvidencePassage,
    EvidenceReference,
    PassageKind,
    PeriodInterpreted,
    Provenance,
    Unit,
)
from carmen.domain.locale import Locale
from carmen.domain.model_output import ModelOutput
from carmen.domain.orchestration.mode import ResponseMode
from carmen.domain.plan import models as plan_models
from carmen.domain.plan.canonical import plan_from_dict
from carmen.domain.plan.models import (
    CrossJoin,
    FactField,
    FactReference,
    Intent,
    PlanLimits,
    PlanStep,
    QueryPlan,
    StepDependency,
)
from carmen.domain.policy.models import AgentAction, Effect, PlatformAction, PolicyDecision
from carmen.domain.role import Role
from carmen.domain.system import SystemId

pytestmark = pytest.mark.contract

CONTRACTS: Final = Path(__file__).resolve().parents[3] / "contracts"
SCHEMA_VERSION: Final = "1.0"

JsonObject = dict[str, object]


def _load(path: Path) -> JsonObject:
    return cast("JsonObject", json.loads(path.read_text(encoding="utf-8")))


@cache
def _schemas() -> dict[str, JsonObject]:
    """Todos los esquemas, por ruta relativa a contracts/ («registry/entities.schema.json»)."""
    return {
        p.relative_to(CONTRACTS).as_posix(): _load(p)
        for p in sorted(CONTRACTS.rglob("*.schema.json"))
    }


@cache
def _registry() -> Registry[Schema]:
    resources = [
        (str(schema["$id"]), Resource.from_contents(schema, default_specification=DRAFT202012))
        for schema in _schemas().values()
    ]
    return Registry[Schema]().with_resources(resources)


def _validator(name: str) -> Draft202012Validator:
    return Draft202012Validator(_schemas()[name], registry=_registry())


def _resolve(name: str, pointer: str) -> JsonObject:
    """El subesquema de `name` en el puntero JSON `pointer` («» es la raíz)."""
    node: object = _schemas()[name]
    for part in filter(None, pointer.split("/")):
        if isinstance(node, list):
            node = node[int(part)]
        else:
            node = cast("Mapping[str, object]", node)[part]
    return cast("JsonObject", node)


# --- 1. Ejemplos positivos y negativos -------------------------------------------------------


@dataclass(frozen=True)
class Example:
    file: str
    schema: str
    index: int
    doc: object
    why: str = ""


def _example_files() -> list[Path]:
    return sorted((CONTRACTS / "examples").rglob("*.json"))


def _examples(kind: str) -> Iterator[Example]:
    for path in _example_files():
        data = _load(path)
        cases = cast("Sequence[object]", data[kind])
        for index, case in enumerate(cases):
            if kind == "valid":
                yield Example(path.name, str(data["schema"]), index, case)
            else:
                negative = cast("Mapping[str, object]", case)
                why = str(negative["why"])
                yield Example(path.name, str(data["schema"]), index, negative["doc"], why)


def _example_id(example: object) -> str:
    assert isinstance(example, Example)
    return f"{example.file}[{example.index}]{' ' + example.why if example.why else ''}"


def test_every_schema_has_examples_and_every_example_names_a_schema() -> None:
    named = {str(_load(p)["schema"]) for p in _example_files()}
    with_examples = {name for name in _schemas() if name != "common.schema.json"}
    assert named == with_examples


@pytest.mark.parametrize("name", sorted(_schemas()))
def test_schema_is_valid_2020_12_with_stable_id(name: str) -> None:
    schema = _schemas()[name]
    Draft202012Validator.check_schema(schema)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["$id"] == f"https://plenergy.internal/carmen/{name}"


@pytest.mark.parametrize("example", list(_examples("valid")), ids=_example_id)
def test_positive_example_is_accepted(example: Example) -> None:
    errors = [e.message for e in _validator(example.schema).iter_errors(example.doc)]
    assert errors == []


@pytest.mark.parametrize("example", list(_examples("invalid")), ids=_example_id)
def test_negative_example_is_rejected(example: Example) -> None:
    assert not _validator(example.schema).is_valid(example.doc), example.why


def test_each_schema_has_at_least_one_negative_example() -> None:
    counts = {name: 0 for name in _schemas() if name != "common.schema.json"}
    for example in _examples("invalid"):
        counts[example.schema] += 1
    assert all(counts.values()), counts


@pytest.mark.parametrize(
    "index", range(len(cast("list[object]", _load(CONTRACTS / "examples/plan.json")["valid"])))
)
def test_positive_plan_examples_build_a_domain_query_plan(index: int) -> None:
    """El esquema y la lectura estricta del dominio (6.2.2) aceptan los mismos planes."""
    doc = cast("list[Mapping[str, object]]", _load(CONTRACTS / "examples/plan.json")["valid"])
    plan = plan_from_dict(doc[index])
    assert isinstance(plan, QueryPlan)


# --- 2. Campo a campo con el dominio ---------------------------------------------------------


@dataclass(frozen=True)
class Alignment:
    """Un objeto del esquema frente a su dataclass del dominio.

    renames: nombre en el esquema → nombre en el dominio.
    schema_only: campos del cable que el dominio deriva o no guarda (con el motivo).
    wire_required: obligatorios en el cable que el dominio rellena por defecto al construir.
    """

    schema: str
    pointer: str
    domain: type
    renames: Mapping[str, str] = field(default_factory=dict)
    schema_only: Mapping[str, str] = field(default_factory=dict)
    wire_required: frozenset[str] = frozenset()

    @property
    def id(self) -> str:
        return f"{self.schema}#{self.pointer or '/'}→{self.domain.__name__}"


_DISCRIMINATOR = {"type": "discriminador de la unión; en el dominio es evidence_type (ClassVar)"}
_VERSIONED = frozenset({"schema_version"})

ALIGNMENTS: Final = (
    # 6.2 plan local
    Alignment(
        "plan.schema.json",
        "",
        QueryPlan,
        schema_only={"systems": "se deriva de los pasos (ADR-043)"},
        wire_required=_VERSIONED,
    ),
    Alignment("plan.schema.json", "/$defs/limits", PlanLimits),
    Alignment("plan.schema.json", "/$defs/crossJoin", CrossJoin),
    Alignment(
        "plan.schema.json", "/$defs/planStep", PlanStep, wire_required=frozenset({"arguments"})
    ),
    Alignment("plan.schema.json", "/$defs/stepDependency", StepDependency),
    Alignment(
        "plan.schema.json",
        "/$defs/factReference",
        FactReference,
        renames={"$ref_step": "step_id", "$ref_fact": "fact", "$ref_field": "field"},
    ),
    # 6.3 evidencia y grounding
    Alignment("evidence.schema.json", "/$defs/entityRef", EntityRef),
    Alignment(
        "evidence.schema.json",
        "/$defs/period",
        PeriodInterpreted,
        renames={"from": "start", "to": "end"},
    ),
    Alignment("evidence.schema.json", "/$defs/provenance", Provenance),
    Alignment("evidence.schema.json", "/$defs/fact", EvidenceFact, schema_only=_DISCRIMINATOR),
    Alignment(
        "evidence.schema.json", "/$defs/passage", EvidencePassage, schema_only=_DISCRIMINATOR
    ),
    Alignment("evidence.schema.json", "/$defs/media", EvidenceMedia, schema_only=_DISCRIMINATOR),
    Alignment("evidence.schema.json", "/$defs/evidenceReference", EvidenceReference),
    Alignment("evidence.schema.json", "/$defs/textSpan", TextSpan),
    Alignment("evidence.schema.json", "/$defs/groundingClaim", GroundingClaim),
    Alignment("evidence.schema.json", "/$defs/groundingResult", GroundingResult),
    # 6.12 orquestación
    Alignment("agent-task.schema.json", "/$defs/taskBudgets", TaskBudgets),
    Alignment("agent-task.schema.json", "/$defs/agentTask", AgentTask),
    Alignment("delegation-plan.schema.json", "", DelegationPlan, wire_required=_VERSIONED),
    Alignment("delegation-plan.schema.json", "/$defs/composition", Composition),
    Alignment("delegation-plan.schema.json", "/$defs/budgets", Budgets),
    Alignment("agent-result.schema.json", "/$defs/warning", AgentWarning),
    Alignment("agent-result.schema.json", "/$defs/needDelegation", NeedDelegation),
    Alignment("agent-result.schema.json", "/$defs/modelOutput", ModelOutput),
    Alignment("agent-result.schema.json", "/$defs/toolCallTrace", ToolCallTrace),
    Alignment("agent-result.schema.json", "/$defs/externalCallTrace", ExternalCallTrace),
    Alignment("agent-result.schema.json", "/$defs/policyDecision", PolicyDecision),
    Alignment("agent-result.schema.json", "/$defs/approvalRecord", ApprovalRecord),
    Alignment("agent-result.schema.json", "/$defs/agentRun", AgentRun),
    Alignment("agent-result.schema.json", "/$defs/agentResult", AgentResult),
    Alignment("agent-card.schema.json", "/$defs/slo", AgentSlo),
    Alignment("agent-card.schema.json", "/$defs/budgets", AgentBudgets),
    Alignment("agent-card.schema.json", "/$defs/agentCard", AgentCard),
    Alignment("conversation-turn.schema.json", "/$defs/tokenUsage", TokenUsage),
    Alignment("conversation-turn.schema.json", "/$defs/conversationTurn", ConversationTurn),
)


def _schema_fields(alignment: Alignment) -> tuple[set[str], set[str]]:
    node = _resolve(alignment.schema, alignment.pointer)
    properties = set(cast("Mapping[str, object]", node["properties"]))
    required = set(cast("Sequence[str]", node.get("required", [])))
    return properties, required


def _domain_fields(domain: type) -> tuple[set[str], set[str]]:
    fields = dataclasses.fields(domain)
    names = {f.name for f in fields}
    required = {
        f.name
        for f in fields
        if f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING
    }
    return names, required


def _to_domain(alignment: Alignment, names: set[str]) -> set[str]:
    return {alignment.renames.get(n, n) for n in names if n not in alignment.schema_only}


@pytest.mark.parametrize("alignment", ALIGNMENTS, ids=lambda a: a.id)
def test_schema_object_matches_domain_type_field_by_field(alignment: Alignment) -> None:
    schema_props, schema_required = _schema_fields(alignment)
    domain_names, domain_required = _domain_fields(alignment.domain)

    assert _to_domain(alignment, schema_props) == domain_names
    wire_required = _to_domain(alignment, schema_required) - alignment.wire_required
    assert wire_required == domain_required


@pytest.mark.parametrize("alignment", ALIGNMENTS, ids=lambda a: a.id)
def test_declared_differences_are_real(alignment: Alignment) -> None:
    """Una excepción que ya no hace falta se borra: la lista no puede pudrirse."""
    schema_props, schema_required = _schema_fields(alignment)
    domain_names, domain_required = _domain_fields(alignment.domain)
    assert set(alignment.renames) <= schema_props
    assert set(alignment.renames.values()) <= domain_names
    assert set(alignment.schema_only) <= schema_props
    assert alignment.wire_required <= schema_required
    assert not alignment.wire_required & domain_required


@pytest.mark.parametrize("alignment", ALIGNMENTS, ids=lambda a: a.id)
def test_domain_objects_are_closed(alignment: Alignment) -> None:
    """Todo objeto alineado rechaza campos desconocidos: lo que no está en el contrato no viaja.

    Un objeto que una raíz envuelve para añadir schema_version se cierra en esa raíz; embebido en
    otro contrato, lo cierra quien lo embebe (lo prueban los ejemplos negativos).
    """
    node = _resolve(alignment.schema, alignment.pointer)
    root = _schemas()[alignment.schema]
    wrapped = root.get("$ref") == f"#{alignment.pointer}" and root["unevaluatedProperties"] is False
    closed = node.get("additionalProperties") is False or node.get("unevaluatedProperties") is False
    assert closed or wrapped


def test_discriminator_matches_domain_class_var() -> None:
    for pointer, domain in (
        ("/$defs/fact", EvidenceFact),
        ("/$defs/passage", EvidencePassage),
        ("/$defs/media", EvidenceMedia),
    ):
        node = _resolve("evidence.schema.json", pointer)
        discriminator = cast("Mapping[str, object]", node["properties"])["type"]
        assert discriminator == {"const": domain.evidence_type}


def test_every_orchestration_dataclass_has_a_contract() -> None:
    """Un tipo nuevo de orquestación sin esquema hace fallar la prueba (6.12)."""
    aligned = {a.domain for a in ALIGNMENTS}
    declared = {
        obj
        for obj in vars(delegation).values()
        if isinstance(obj, type)
        and dataclasses.is_dataclass(obj)
        and obj.__module__ == delegation.__name__
    }
    assert declared <= aligned


def test_schema_versions_match_domain_constants() -> None:
    common = _resolve("common.schema.json", "/$defs/schemaVersion")
    assert common == {"const": SCHEMA_VERSION}
    assert plan_models.SCHEMA_VERSION == SCHEMA_VERSION
    plan_default = next(f for f in dataclasses.fields(DelegationPlan) if f.name == "schema_version")
    assert plan_default.default == SCHEMA_VERSION
    sse_version = _resolve("sse-events.schema.json", "/properties/schema_version")
    assert sse_version == {"const": "1.1"}


# --- 3. Enumerados, identificadores y errores ------------------------------------------------

SSE_EVENT_TYPES: Final = (
    "mode", "stage", "delegation", "tool_call", "tool_result", "agent_result",
    "approval_required", "delta", "grounding", "warning", "error", "done",
)  # fmt: skip


def _values(enum: type[StrEnum]) -> list[str]:
    return [member.value for member in enum]


ENUMS: Final[tuple[tuple[str, str, Sequence[str]], ...]] = (
    ("common.schema.json", "/$defs/locale", _values(Locale)),
    ("common.schema.json", "/$defs/role", _values(Role)),
    ("common.schema.json", "/$defs/effect", _values(Effect)),
    ("common.schema.json", "/$defs/purpose", _values(Purpose)),
    ("common.schema.json", "/$defs/dataClass", _values(DataClass)),
    ("common.schema.json", "/$defs/responseMode", _values(ResponseMode)),
    ("plan.schema.json", "/$defs/intent", _values(Intent)),
    ("plan.schema.json", "/$defs/factReference/properties/$ref_field", get_args(FactField)),
    ("evidence.schema.json", "/$defs/unit", _values(Unit)),
    ("evidence.schema.json", "/$defs/passageKind", get_args(PassageKind)),
    ("evidence.schema.json", "/$defs/groundingClaim/properties/verdict", get_args(Verdict)),
    ("agent-task.schema.json", "/$defs/expects", _values(Expects)),
    ("agent-result.schema.json", "/$defs/status", _values(AgentResultStatus)),
    (
        "agent-result.schema.json",
        "/$defs/needDelegation/properties/reason",
        _values(NeedDelegationReason),
    ),
    (
        "agent-result.schema.json",
        "/$defs/needDelegation/properties/suggested_domain",
        _values(AgentDomain),
    ),
    (
        "agent-result.schema.json",
        "/$defs/policyDecision/properties/action",
        _values(AgentAction) + _values(PlatformAction),
    ),
    (
        "agent-result.schema.json",
        "/$defs/policyDecision/allOf/0/if/properties/action",
        _values(AgentAction),
    ),
    (
        "agent-result.schema.json",
        "/$defs/approvalRecord/properties/status",
        _values(ApprovalStatus),
    ),
    ("agent-card.schema.json", "/$defs/lifecycle", _values(AgentLifecycleState)),
    ("agent-card.schema.json", "/$defs/visibility", _values(Visibility)),
    ("agent-card.schema.json", "/$defs/connectivity", _values(Connectivity)),
    ("delegation-plan.schema.json", "/$defs/composition/properties/kind", _values(CompositionKind)),
    (
        "delegation-plan.schema.json",
        "/properties/response_mode",
        [m.value for m in ResponseMode if m.delegates],
    ),
    ("conversation-turn.schema.json", "/$defs/status", _values(TurnStatus)),
    (
        "conversation-turn.schema.json",
        "/$defs/conversationTurn/allOf/0/if/properties/response_mode",
        [m.value for m in ResponseMode if not m.delegates],
    ),
    (
        "sse-events.schema.json",
        "/$defs/approval_requiredPayload/properties/impact",
        _values(Impact),
    ),
)


@pytest.mark.parametrize(("schema", "pointer", "expected"), ENUMS, ids=lambda v: str(v)[:60])
def test_enum_matches_domain(schema: str, pointer: str, expected: Sequence[str]) -> None:
    assert _resolve(schema, pointer)["enum"] == list(expected)


IDENTIFIERS: Final[tuple[tuple[str, type[ids.PatternId]], ...]] = (
    ("agentId", ids.AgentId),
    ("systemId", SystemId),
    ("stepId", ids.StepId),
    ("taskId", ids.TaskId),
    ("planId", ids.PlanId),
    ("delegationPlanId", ids.DelegationPlanId),
    ("turnId", ids.TurnId),
    ("conversationId", ids.ConversationId),
    ("principalId", ids.PrincipalId),
    ("runId", ids.RunId),
    ("approvalId", ids.ApprovalId),
    ("callId", ids.CallId),
    ("correlationId", ids.CorrelationId),
    ("localId", ids.FactId),
    ("dottedId", ids.RoleId),
    ("dottedId", ids.Scope),
    ("providerId", ids.ProviderId),
    ("mcpServerId", ids.McpServerId),
    ("delegatedIdentityRef", ids.DelegatedIdentityRef),
)


@pytest.mark.parametrize(("definition", "domain"), IDENTIFIERS, ids=lambda v: str(v))
def test_identifier_pattern_matches_domain(definition: str, domain: type[ids.PatternId]) -> None:
    node = _resolve("common.schema.json", f"/$defs/{definition}")
    assert node["pattern"] == domain.pattern.pattern


def _error_classes() -> Iterator[type[domain_errors.CarmenError]]:
    pending: list[type[domain_errors.CarmenError]] = [domain_errors.CarmenError]
    while pending:
        cls = pending.pop()
        pending.extend(cls.__subclasses__())
        yield cls


#: Familias abstractas: agrupan códigos, nunca se lanzan ni viajan.
ABSTRACT_ERRORS: Final = frozenset({"carmen_error", "mcp_error", "llm_error"})


def test_error_catalog_matches_domain_errors() -> None:
    catalog = cast("list[Mapping[str, object]]", _load(CONTRACTS / "errors.json")["errors"])
    by_code = {str(entry["code"]): entry for entry in catalog}
    domain = {cls.code: cls.__name__ for cls in _error_classes() if cls.code not in ABSTRACT_ERRORS}
    assert len(by_code) == len(catalog)
    assert set(by_code) == set(domain)
    assert {code: str(entry["class"]) for code, entry in by_code.items()} == domain
    for entry in catalog:  # la traducción a SSE solo usa eventos que existen en SSE 1.1
        assert set(str(entry["sse"]).split("+")) <= set(SSE_EVENT_TYPES), entry


# --- Contratos sin tipo de dominio todavía: tablas fijadas ----------------------------------

# (obligatorios, opcionales) por objeto. Sus tipos llegan con los adaptadores (Prompts 7, 11, 15)
# y entonces pasan a ALIGNMENTS; hasta entonces, esta tabla es el «tipo» de Python.
PINNED: Final[Mapping[tuple[str, str], tuple[frozenset[str], frozenset[str]]]] = {
    ("mcp-envelope.schema.json", ""): (
        frozenset(
            {
                "schema_version",
                "system_id",
                "tool_name",
                "call_id",
                "correlation_id",
                "generated_at",
                "catalog_version",
                "facts",
                "passages",
                "media",
                "warnings",
                "partial",
            }
        ),
        frozenset({"period_interpreted", "rows", "next_cursor"}),
    ),
    ("mcp-envelope.schema.json", "/$defs/fact"): (
        frozenset({"key", "label", "value"}),
        frozenset({"metric", "unit", "entity", "dimensions"}),
    ),
    ("mcp-envelope.schema.json", "/$defs/passage"): (
        frozenset({"passage_id", "document_id", "title", "text", "kind", "relevance"}),
        frozenset({"section", "anchor", "doc_version", "updated_at", "url"}),
    ),
    ("mcp-envelope.schema.json", "/$defs/media"): (
        frozenset({"media_id", "document_id", "mime", "caption", "uri"}),
        frozenset({"bytes", "anchor"}),
    ),
    ("mcp-envelope.schema.json", "/$defs/warning"): (frozenset({"code", "message"}), frozenset()),
    ("mcp-servers.schema.json", ""): (frozenset({"schema_version", "servers"}), frozenset()),
    ("mcp-servers.schema.json", "/$defs/server"): (
        frozenset(
            {
                "id",
                "display_name",
                "routing_description",
                "transport",
                "identity",
                "timeouts",
                "limits",
                "contract",
                "capabilities",
                "content",
                "enabled",
            }
        ),
        frozenset(),
    ),
    ("mcp-servers.schema.json", "/$defs/transport"): (
        frozenset({"kind", "url"}),
        frozenset({"tls"}),
    ),
    ("mcp-servers.schema.json", "/$defs/tls"): (
        frozenset({"client_cert", "client_key", "ca_bundle", "verify"}),
        frozenset(),
    ),
    ("mcp-servers.schema.json", "/$defs/identity"): (
        frozenset({"audience", "scopes"}),
        frozenset(),
    ),
    ("mcp-servers.schema.json", "/$defs/timeouts"): (
        frozenset({"connect_ms", "call_ms"}),
        frozenset(),
    ),
    ("mcp-servers.schema.json", "/$defs/limits"): (
        frozenset({"max_concurrency", "max_rows"}),
        frozenset(),
    ),
    ("mcp-servers.schema.json", "/$defs/contract"): (
        frozenset({"min_envelope_version"}),
        frozenset(),
    ),
    ("sse-events.schema.json", ""): (
        frozenset(
            {
                "schema_version",
                "event_id",
                "event_type",
                "correlation_id",
                "sequence",
                "timestamp",
                "payload",
            }
        ),
        frozenset(),
    ),
    ("sse-events.schema.json", "/$defs/modePayload"): (frozenset({"response_mode"}), frozenset()),
    ("sse-events.schema.json", "/$defs/stagePayload"): (
        frozenset({"stage"}),
        frozenset({"detail", "step_id"}),
    ),
    ("sse-events.schema.json", "/$defs/delegationPayload"): (
        frozenset({"task_id", "agent_id", "depends_on"}),
        frozenset(),
    ),
    ("sse-events.schema.json", "/$defs/tool_callPayload"): (
        frozenset(
            {
                "agent_id",
                "task_id",
                "step_id",
                "call_id",
                "system_id",
                "tool_name",
                "arguments_digest",
            }
        ),
        frozenset(),
    ),
    ("sse-events.schema.json", "/$defs/tool_resultPayload"): (
        frozenset(
            {"agent_id", "task_id", "step_id", "call_id", "ok", "facts_count", "ms", "partial"}
        ),
        frozenset(),
    ),
    ("sse-events.schema.json", "/$defs/agent_resultPayload"): (
        frozenset({"task_id", "agent_id", "status", "evidence_count", "ms"}),
        frozenset(),
    ),
    ("sse-events.schema.json", "/$defs/approval_requiredPayload"): (
        frozenset({"request_id", "agent_id", "summary", "impact", "expires_at"}),
        frozenset(),
    ),
    ("sse-events.schema.json", "/$defs/deltaPayload"): (
        frozenset({"section", "text"}),
        frozenset(),
    ),
    ("sse-events.schema.json", "/$defs/groundingPayload"): (
        frozenset({"ok", "checked", "unsupported"}),
        frozenset(),
    ),
    ("sse-events.schema.json", "/$defs/warningPayload"): (
        frozenset({"code", "message"}),
        frozenset({"system_id", "agent_id"}),
    ),
    ("sse-events.schema.json", "/$defs/errorPayload"): (
        frozenset({"code", "message", "recoverable"}),
        frozenset(),
    ),
    ("sse-events.schema.json", "/$defs/donePayload"): (
        frozenset(
            {
                "message_id",
                "conversation_id",
                "status",
                "partial",
                "missing_systems",
                "grounding_ok",
                "plan_id",
                "round",
                "repairs",
                "latency_ms",
                "model",
                "catalog_versions",
                "response_mode",
                "agents_used",
                "missing_agents",
            }
        ),
        frozenset(),
    ),
    ("registry/agent-mcp-bindings.schema.json", "/$defs/binding"): (
        frozenset({"agent_id", "mcp_server", "scopes", "actions", "active"}),
        frozenset(),
    ),
    ("registry/agent-provider-bindings.schema.json", "/$defs/binding"): (
        frozenset({"agent_id", "provider", "purposes", "max_classification", "active"}),
        frozenset({"region"}),
    ),
    ("registry/model-providers.schema.json", "/$defs/provider"): (
        frozenset({"id", "kind", "region", "models", "retention_days", "active"}),
        frozenset({"contract_ref"}),
    ),
    ("registry/external-sources.schema.json", "/$defs/source"): (
        frozenset({"id", "domains", "kind", "reliability", "agents", "active"}),
        frozenset(),
    ),
    ("registry/agent-mcp-bindings.schema.json", ""): (
        frozenset({"schema_version", "bindings"}),
        frozenset(),
    ),
    ("registry/agent-provider-bindings.schema.json", ""): (
        frozenset({"schema_version", "bindings"}),
        frozenset(),
    ),
    ("registry/model-providers.schema.json", ""): (
        frozenset({"schema_version", "providers"}),
        frozenset(),
    ),
    ("registry/external-sources.schema.json", ""): (
        frozenset({"schema_version", "sources"}),
        frozenset(),
    ),
    ("registry/entities.schema.json", ""): (
        frozenset({"schema_version", "entidades"}),
        frozenset(),
    ),
    ("registry/egress-policy.schema.json", ""): (
        frozenset({"schema_version", "default", "policies"}),
        frozenset(),
    ),
    ("registry/egress-policy.schema.json", "/$defs/policy"): (
        frozenset(
            {
                "policy_id",
                "agents",
                "allowlist_domains",
                "methods",
                "max_bytes",
                "max_requests_per_run",
                "max_cost_per_run_eur",
                "allowed_classifications",
                "redactions",
                "retention_days",
                "region",
            }
        ),
        frozenset(),
    ),
    ("registry/entities.schema.json", "/$defs/entity"): (
        frozenset({"identificador_canonico", "mapeo"}),
        frozenset({"formato", "descripcion"}),
    ),
    ("registry/entities.schema.json", "/$defs/mapping"): (frozenset({"campo", "via"}), frozenset()),
}


@pytest.mark.parametrize("key", sorted(PINNED), ids=lambda k: f"{k[0]}#{k[1] or '/'}")
def test_pinned_contract_fields(key: tuple[str, str]) -> None:
    required, optional = PINNED[key]
    node = _resolve(*key)
    properties = set(cast("Mapping[str, object]", node["properties"]))
    assert set(cast("Sequence[str]", node.get("required", []))) == required
    assert properties == required | optional


def test_every_object_in_every_schema_is_aligned_or_pinned() -> None:
    """Ningún objeto con propiedades queda sin comprobar: o tiene tipo, o tiene tabla."""
    checked = {(a.schema, a.pointer) for a in ALIGNMENTS} | set(PINNED)
    wrappers = {
        (name, "")
        for name, schema in _schemas().items()
        if set(cast("Mapping[str, object]", schema.get("properties", {}))) == {"schema_version"}
    }
    objects = {
        (name, pointer)
        for name, schema in _schemas().items()
        for pointer in ["", *(f"/$defs/{d}" for d in cast("JsonObject", schema.get("$defs", {})))]
        if "properties" in _resolve(name, pointer)
    }
    assert objects - wrappers == checked


def test_sse_event_types_each_have_exactly_one_payload() -> None:
    schema = _schemas()["sse-events.schema.json"]
    assert _resolve("sse-events.schema.json", "/properties/event_type")["enum"] == list(
        SSE_EVENT_TYPES
    )
    branches = cast("list[Mapping[str, Mapping[str, object]]]", schema["allOf"])
    routed = {}
    for branch in branches:
        condition = cast("Mapping[str, Mapping[str, object]]", branch["if"]["properties"])
        target = cast("Mapping[str, Mapping[str, object]]", branch["then"]["properties"])
        routed[condition["event_type"]["const"]] = target["payload"]["$ref"]
    assert routed == {t: f"#/$defs/{t}Payload" for t in SSE_EVENT_TYPES}
