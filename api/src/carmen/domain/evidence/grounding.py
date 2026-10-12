"""Resultado del verificador de anclaje: cada cifra narrada, con su respaldo o sin él (6.3).

Los tipos se construyen coherentes o no se construyen: una afirmación respaldada sin referencia,
o un resultado ok con afirmaciones sin respaldo, son imposibles de representar.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from carmen.domain.errors import ValidationError
from carmen.domain.evidence.models import EvidenceReference
from carmen.domain.ids import ClaimId

Verdict = Literal["supported", "unsupported", "whitelisted"]


@dataclass(frozen=True, slots=True)
class TextSpan:
    """Posición de una afirmación en la respuesta narrada: [start, end) en caracteres."""

    start: int
    end: int

    def __post_init__(self) -> None:
        if not 0 <= self.start < self.end:
            msg = f"tramo de texto inválido: [{self.start}, {self.end})"
            raise ValidationError(msg)

    @property
    def length(self) -> int:
        return self.end - self.start


@dataclass(frozen=True, slots=True)
class GroundingClaim:
    claim_id: ClaimId
    text_span: TextSpan
    raw_value: str
    normalized: Decimal | None
    supported_by: EvidenceReference | None
    verdict: Verdict
    reason: str | None = None

    def __post_init__(self) -> None:
        if len(self.raw_value) != self.text_span.length:
            msg = f"{self.claim_id}: raw_value no ocupa exactamente su tramo de texto"
            raise ValidationError(msg)
        if self.verdict == "supported":
            if self.supported_by is None or self.normalized is None:
                msg = f"{self.claim_id}: supported exige referencia y valor normalizado"
                raise ValidationError(msg)
        elif self.verdict in ("unsupported", "whitelisted"):
            if self.supported_by is not None:
                msg = f"{self.claim_id}: {self.verdict} no puede llevar referencia"
                raise ValidationError(msg)
            if not self.reason:
                msg = f"{self.claim_id}: {self.verdict} exige un motivo"
                raise ValidationError(msg)
        else:
            msg = f"{self.claim_id}: veredicto desconocido {self.verdict!r}"
            raise ValidationError(msg)


@dataclass(frozen=True, slots=True)
class GroundingResult:
    ok: bool
    checked: int
    claims: tuple[GroundingClaim, ...]
    unsupported: tuple[ClaimId, ...]

    def __post_init__(self) -> None:
        ids = [claim.claim_id for claim in self.claims]
        if len(set(ids)) != len(ids):
            msg = "el resultado de anclaje repite afirmaciones"
            raise ValidationError(msg)
        expected = tuple(c.claim_id for c in self.claims if c.verdict == "unsupported")
        if self.checked != len(self.claims):
            msg = f"checked={self.checked} no coincide con {len(self.claims)} afirmaciones"
            raise ValidationError(msg)
        if self.unsupported != expected:
            msg = "unsupported no coincide con las afirmaciones sin respaldo"
            raise ValidationError(msg)
        if self.ok != (not expected):
            msg = "ok solo es verdadero cuando no hay afirmaciones sin respaldo"
            raise ValidationError(msg)

    @classmethod
    def of(cls, claims: tuple[GroundingClaim, ...]) -> "GroundingResult":
        """Deriva ok, checked y unsupported de las afirmaciones."""
        unsupported = tuple(c.claim_id for c in claims if c.verdict == "unsupported")
        return cls(ok=not unsupported, checked=len(claims), claims=claims, unsupported=unsupported)
