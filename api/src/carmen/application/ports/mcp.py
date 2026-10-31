"""Cliente MCP del ejecutor de agente y sobre de respuesta (5.5, 6.4).

Solo lo usa el ejecutor de agente: el supervisor no puede importarlo (5.14.6). Los tipos del sobre
coinciden campo a campo con contracts/mcp-envelope.schema.json.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import Final, Protocol

from carmen.application.context import ExecutionContext
from carmen.application.jsontypes import JsonObject
from carmen.application.ports.identity import DelegatedToken
from carmen.domain.errors import ValidationError
from carmen.domain.evidence.models import EntityRef, FactValue, PassageKind, PeriodInterpreted, Unit
from carmen.domain.ids import CallId, CorrelationId, MediaId, PassageId, StepId
from carmen.domain.plan.models import Scalar
from carmen.domain.system import SystemId
from carmen.domain.text import require_non_negative, require_text
from carmen.domain.time import Instant

ENVELOPE_VERSION: Final = "1.0"
MAX_ROWS: Final = 500
_TOOL_NAME: Final = re.compile(r"^[a-z][a-z0-9_]{1,47}$")


@dataclass(frozen=True, slots=True)
class EnvelopeFact:
    key: str
    label: str
    value: FactValue
    metric: str | None = None
    unit: Unit | None = None
    entity: EntityRef | None = None
    dimensions: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_text("key", self.key)
        require_text("label", self.label)
        object.__setattr__(self, "dimensions", MappingProxyType(dict(self.dimensions)))


@dataclass(frozen=True, slots=True)
class EnvelopePassage:
    passage_id: PassageId
    document_id: str
    title: str
    text: str
    kind: PassageKind
    relevance: float
    section: str | None = None
    anchor: str | None = None
    doc_version: str | None = None
    updated_at: Instant | None = None
    url: str | None = None


@dataclass(frozen=True, slots=True)
class EnvelopeMedia:
    media_id: MediaId
    document_id: str
    mime: str
    caption: str
    uri: str
    bytes: int | None = None
    anchor: str | None = None


@dataclass(frozen=True, slots=True)
class EnvelopeWarning:
    code: str
    message: str

    def __post_init__(self) -> None:
        require_text("code", self.code)
        require_text("message", self.message)


RowValue = Decimal | int | str | bool | None


@dataclass(frozen=True, slots=True)
class McpEnvelope:
    """Respuesta SIEMPRE estructurada de una herramienta. Los pasajes y adjuntos se validan al
    convertirse en evidencia (EvidencePassage, EvidenceMedia), que es donde viven sus reglas.
    """

    schema_version: str
    system_id: SystemId
    tool_name: str
    call_id: CallId
    correlation_id: CorrelationId
    generated_at: Instant
    catalog_version: str
    facts: tuple[EnvelopeFact, ...]
    passages: tuple[EnvelopePassage, ...]
    media: tuple[EnvelopeMedia, ...]
    warnings: tuple[EnvelopeWarning, ...]
    partial: bool
    period_interpreted: PeriodInterpreted | None = None
    rows: tuple[Mapping[str, RowValue], ...] = ()
    next_cursor: str | None = None

    def __post_init__(self) -> None:
        if self.schema_version != ENVELOPE_VERSION:
            msg = f"versión de sobre no admitida: {self.schema_version!r}"
            raise ValidationError(msg)
        require_text("catalog_version", self.catalog_version)
        if self.partial and not self.warnings:
            msg = "un sobre parcial explica qué falta con al menos un aviso"
            raise ValidationError(msg)
        if len(self.rows) > MAX_ROWS:
            msg = f"el sobre trae {len(self.rows)} filas; máximo {MAX_ROWS}"
            raise ValidationError(msg)
        keys = [f.key for f in self.facts]
        if len(set(keys)) != len(keys):
            msg = "el sobre repite la clave de un hecho"
            raise ValidationError(msg)
        object.__setattr__(self, "rows", tuple(MappingProxyType(dict(r)) for r in self.rows))


@dataclass(frozen=True, slots=True)
class ToolDescriptor:
    system: SystemId
    name: str
    description: str
    input_schema: JsonObject
    catalog_version: str

    def __post_init__(self) -> None:
        if not _TOOL_NAME.fullmatch(self.name):
            msg = f"nombre de herramienta inválido: {self.name!r}"
            raise ValidationError(msg)
        require_text("description", self.description)
        require_text("catalog_version", self.catalog_version)


ResolvedArgument = Scalar | tuple[Scalar, ...]


@dataclass(frozen=True, slots=True)
class ToolInvocation:
    """Una llamada ya resuelta: las referencias a hechos se sustituyeron por sus valores."""

    call_id: CallId
    step_id: StepId
    system: SystemId
    tool: str
    arguments: Mapping[str, ResolvedArgument]
    token: DelegatedToken

    def __post_init__(self) -> None:
        if not _TOOL_NAME.fullmatch(self.tool):
            msg = f"nombre de herramienta inválido: {self.tool!r}"
            raise ValidationError(msg)
        object.__setattr__(self, "arguments", MappingProxyType(dict(self.arguments)))


class HealthStatus(StrEnum):
    UP = "up"
    DEGRADED = "degraded"
    DOWN = "down"


@dataclass(frozen=True, slots=True)
class SystemHealth:
    system: SystemId
    status: HealthStatus
    checked_at: Instant
    latency_ms: int | None = None
    detail: str | None = None

    def __post_init__(self) -> None:
        if self.latency_ms is not None:
            require_non_negative("latency_ms", self.latency_ms)


class McpClientPort(Protocol):
    async def list_tools(self, system: SystemId, ctx: ExecutionContext) -> list[ToolDescriptor]:
        """Lanza: McpUnavailableError, McpTimeoutError, McpUnauthorizedError."""
        ...

    async def call_tool(self, invocation: ToolInvocation, ctx: ExecutionContext) -> McpEnvelope:
        """Devuelve SIEMPRE un sobre estructurado (6.4).

        Lanza: McpUnavailableError, McpTimeoutError, McpForbiddenError, McpToolError,
        McpContractViolationError.
        """
        ...

    async def health(self, system: SystemId) -> SystemHealth:
        """No lanza: un sistema que no responde está DOWN."""
        ...
