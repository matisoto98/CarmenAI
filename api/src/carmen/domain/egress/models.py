"""Exportación de datos: si ESTOS datos pueden ir a ESE destino (5.15.5, 6.12.7).

Autorizar un agente no autoriza la exportación. La decisión se toma por dato, no por agente, y
se evalúa ANTES de construir la petición externa.
"""

from dataclasses import dataclass
from enum import StrEnum

from carmen.domain.ids import ProviderId
from carmen.domain.policy.models import Effect
from carmen.domain.text import require_text
from carmen.domain.time import Instant


class DataClass(StrEnum):
    """Clasificación del dato, de menor a mayor sensibilidad (7.10, ADR-044).

    Taxonomía provisional tomada de los ejemplos del documento maestro, hasta que Plenergy
    valide la suya (P2, P18).
    """

    PUBLICO = "PUBLICO"
    INTERNO = "INTERNO"
    CONFIDENCIAL = "CONFIDENCIAL"

    @property
    def level(self) -> int:
        return list(DataClass).index(self)

    def fits_within(self, ceiling: "DataClass") -> bool:
        """True si un dato de esta clase cabe bajo la clasificación máxima dada."""
        return self.level <= ceiling.level


class Purpose(StrEnum):
    """Finalidad declarada de una llamada a un proveedor (7.10.1)."""

    ROUTING = "routing"
    NARRATION = "narration"
    ANALYSIS = "analysis"


@dataclass(frozen=True, slots=True)
class Destination:
    provider: ProviderId
    model: str
    region: str

    def __post_init__(self) -> None:
        require_text("destination.model", self.model)
        require_text("destination.region", self.region)


@dataclass(frozen=True, slots=True)
class DataExportDecision:
    decision: Effect
    classification: DataClass
    destination: Destination
    purpose: Purpose
    policy_id: str
    redactions: tuple[str, ...]
    reason: str
    decided_at: Instant

    def __post_init__(self) -> None:
        require_text("policy_id", self.policy_id)
        require_text("reason", self.reason)  # obligatorio también en allow
        for redaction in self.redactions:
            require_text("redactions", redaction)

    @property
    def allowed(self) -> bool:
        return self.decision is Effect.ALLOW
