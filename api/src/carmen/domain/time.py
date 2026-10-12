"""Instantes con zona horaria explícita."""

from dataclasses import dataclass
from datetime import UTC, datetime

from carmen.domain.errors import ValidationError


@dataclass(frozen=True, slots=True, order=True)
class Instant:
    """Un instante absoluto. Se rechaza cualquier datetime sin zona."""

    at: datetime

    def __post_init__(self) -> None:
        if self.at.tzinfo is None or self.at.utcoffset() is None:
            msg = "Instant exige un datetime con zona horaria"
            raise ValidationError(msg)
        object.__setattr__(self, "at", self.at.astimezone(UTC))

    @classmethod
    def parse(cls, text: str) -> "Instant":
        """Lee un instante ISO 8601 con zona, como 2026-07-27T09:14:22Z."""
        try:
            return cls(datetime.fromisoformat(text))
        except ValueError as exc:
            msg = f"instante ISO 8601 inválido: {text!r}"
            raise ValidationError(msg) from exc

    def isoformat(self) -> str:
        return self.at.isoformat().replace("+00:00", "Z")
