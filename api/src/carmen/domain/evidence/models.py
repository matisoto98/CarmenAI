"""Evidencia: la fuente primaria recuperada, nunca la respuesta de un modelo (6.3, 6.9.2).

La evidencia es una unión discriminada de tres tipos con identificador propio: un hecho devuelto
por una herramienta, un pasaje literal de un documento con su procedencia, o un adjunto
referenciado. Un pasaje no sirve donde se exige un hecho numérico, ni por tipo ni en ejecución.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import ClassVar, Final, Literal

from carmen.domain.errors import ValidationError
from carmen.domain.ids import CallId, FactId, MediaId, PassageId
from carmen.domain.system import SystemId
from carmen.domain.time import Instant

_MIME: Final = re.compile(r"^[a-z]+/[a-z0-9.+-]+$")

FactValue = Decimal | int | str | bool | None
PassageKind = Literal["reference", "procedure", "warning", "definition"]


class Unit(StrEnum):
    """Unidades que declara el sistema de origen junto al valor (6.4)."""

    COUNT = "count"
    PERCENT = "percent"
    RATIO = "ratio"
    MILLISECONDS = "ms"
    SECONDS = "seconds"
    MINUTES = "minutes"
    HOURS = "hours"
    DAYS = "days"
    EUR = "eur"
    LITERS = "liters"


def _require_text(name: str, value: str) -> None:
    if not value.strip():
        msg = f"{name} no puede estar vacío"
        raise ValidationError(msg)


@dataclass(frozen=True, slots=True)
class EntityRef:
    """Entidad a la que se refiere un hecho: tipo e identificador en el sistema de origen."""

    type: str
    id: str
    name: str | None = None

    def __post_init__(self) -> None:
        _require_text("entity.type", self.type)
        _require_text("entity.id", self.id)


@dataclass(frozen=True, slots=True)
class PeriodInterpreted:
    """Periodo que el sistema entendió, declarado con su texto legible (6.4)."""

    expression: str
    start: Instant
    end: Instant
    text: str

    def __post_init__(self) -> None:
        _require_text("period.expression", self.expression)
        _require_text("period.text", self.text)
        if self.end < self.start:
            msg = "el periodo termina antes de empezar"
            raise ValidationError(msg)


@dataclass(frozen=True, slots=True)
class Provenance:
    """De dónde sale un hecho: herramienta, versión de catálogo y frescura."""

    tool_name: str
    catalog_version: str
    generated_at: Instant

    def __post_init__(self) -> None:
        _require_text("provenance.tool_name", self.tool_name)
        _require_text("provenance.catalog_version", self.catalog_version)


@dataclass(frozen=True, slots=True)
class EvidenceFact:
    evidence_type: ClassVar[Literal["fact"]] = "fact"

    fact_id: FactId
    call_id: CallId
    system_id: SystemId
    label: str
    value: FactValue
    provenance: Provenance
    metric: str | None = None
    unit: Unit | None = None
    entity: EntityRef | None = None
    dimensions: Mapping[str, str] = field(default_factory=dict)
    period: PeriodInterpreted | None = None

    def __post_init__(self) -> None:
        _require_text("label", self.label)
        value: object = self.value  # puede llegar sin tipar desde el sobre MCP
        if isinstance(value, float) or not isinstance(value, Decimal | int | str | bool | None):
            msg = f"valor de hecho no admitido: {type(value).__name__}"
            raise ValidationError(msg)
        if isinstance(value, Decimal) and not value.is_finite():
            msg = "el valor de un hecho debe ser finito"
            raise ValidationError(msg)
        if self.metric is not None:
            _require_text("metric", self.metric)
        object.__setattr__(self, "dimensions", MappingProxyType(dict(self.dimensions)))

    @property
    def is_numeric(self) -> bool:
        return isinstance(self.value, Decimal | int) and not isinstance(self.value, bool)

    @property
    def numeric_value(self) -> Decimal:
        """El valor como Decimal. Solo para hechos numéricos."""
        if isinstance(self.value, bool) or not isinstance(self.value, Decimal | int):
            msg = f"el hecho {self.fact_id} no es numérico"
            raise ValidationError(msg)
        return Decimal(self.value)


@dataclass(frozen=True, slots=True)
class EvidencePassage:
    evidence_type: ClassVar[Literal["passage"]] = "passage"

    passage_id: PassageId
    call_id: CallId
    system_id: SystemId
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

    def __post_init__(self) -> None:
        _require_text("document_id", self.document_id)
        _require_text("title", self.title)
        _require_text("text", self.text)
        if self.kind not in ("reference", "procedure", "warning", "definition"):
            msg = f"tipo de pasaje desconocido: {self.kind!r}"
            raise ValidationError(msg)
        if isinstance(self.relevance, bool) or not 0.0 <= self.relevance <= 1.0:
            msg = f"relevance fuera de [0, 1]: {self.relevance!r}"
            raise ValidationError(msg)
        if self.kind == "procedure" and self.updated_at is None:
            msg = "un procedimiento exige updated_at: un runbook viejo es peligroso (6.9.2)"
            raise ValidationError(msg)


@dataclass(frozen=True, slots=True)
class EvidenceMedia:
    evidence_type: ClassVar[Literal["media"]] = "media"

    media_id: MediaId
    call_id: CallId
    system_id: SystemId
    document_id: str
    mime: str
    caption: str
    uri: str
    bytes: int | None = None
    anchor: str | None = None

    def __post_init__(self) -> None:
        _require_text("document_id", self.document_id)
        _require_text("caption", self.caption)
        _require_text("uri", self.uri)
        if not _MIME.fullmatch(self.mime):
            msg = f"tipo MIME inválido: {self.mime!r}"
            raise ValidationError(msg)
        if self.uri.strip().lower().startswith("data:"):
            msg = "un adjunto viaja como referencia autenticada, nunca incrustado (6.9.2)"
            raise ValidationError(msg)
        if self.bytes is not None and (isinstance(self.bytes, bool) or self.bytes < 0):
            msg = f"bytes inválido: {self.bytes!r}"
            raise ValidationError(msg)


EvidenceItem = EvidenceFact | EvidencePassage | EvidenceMedia


@dataclass(frozen=True, slots=True)
class EvidenceReference:
    """Enlace de una cifra con el hecho que la respalda."""

    call_id: CallId
    fact_id: FactId

    @classmethod
    def to(cls, fact: EvidenceFact) -> "EvidenceReference":
        return cls(fact.call_id, fact.fact_id)


def require_numeric_fact(item: EvidenceItem) -> EvidenceFact:
    """Devuelve el hecho si es numérico. Un pasaje o un adjunto nunca respaldan una cifra."""
    if not isinstance(item, EvidenceFact):
        msg = f"se exige un hecho numérico y llegó evidencia de tipo {item.evidence_type}"
        raise ValidationError(msg)
    if not item.is_numeric:
        msg = f"el hecho {item.fact_id} no es numérico"
        raise ValidationError(msg)
    return item
