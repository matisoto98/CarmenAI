"""ModelOutput: texto generado por un modelo. NUNCA es evidencia (6.3, 5.15.4).

Sirve para redactar, resumir o clasificar. No comparte base con EvidenceFact, EvidencePassage
ni EvidenceMedia, de modo que no puede colarse donde se espera evidencia ni respaldar una cifra.
"""

from dataclasses import dataclass
from decimal import Decimal

from carmen.domain.egress.models import Purpose
from carmen.domain.errors import ValidationError
from carmen.domain.ids import ProviderId
from carmen.domain.text import require_non_negative, require_text
from carmen.domain.time import Instant


@dataclass(frozen=True, slots=True)
class ModelOutput:
    provider: ProviderId
    model: str
    model_version: str
    purpose: Purpose
    text: str
    tokens_in: int
    tokens_out: int
    cost_eur: Decimal
    produced_at: Instant

    def __post_init__(self) -> None:
        require_text("model", self.model)
        require_text("model_version", self.model_version)
        require_non_negative("tokens_in", self.tokens_in)
        require_non_negative("tokens_out", self.tokens_out)
        if not self.cost_eur.is_finite() or self.cost_eur < 0:
            msg = "cost_eur debe ser >= 0"
            raise ValidationError(msg)
