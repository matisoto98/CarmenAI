"""Comprobaciones de texto comunes a los contratos del dominio."""

from carmen.domain.errors import ValidationError


def require_text(name: str, value: str) -> None:
    """Rechaza una cadena vacía o hecha solo de espacios."""
    if not isinstance(value, str) or not value.strip():
        msg = f"{name} no puede estar vacío"
        raise ValidationError(msg)


def require_non_negative(name: str, value: int) -> None:
    """Rechaza un entero negativo o un booleano disfrazado de entero."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        msg = f"{name} debe ser un entero >= 0: {value!r}"
        raise ValidationError(msg)
