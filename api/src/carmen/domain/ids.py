"""Identificadores tipados del dominio.

Cada identificador es un str inmutable que valida su forma al construirse, de modo que un
PlanId no se confunde con un CallId ni en el tipado ni en tiempo de ejecución.
"""

import re
from typing import ClassVar, Self

from carmen.domain.errors import ValidationError


class PatternId(str):
    """Base de los identificadores: un str que solo se construye si cumple su patrón."""

    __slots__ = ()
    pattern: ClassVar[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")

    def __new__(cls, value: str) -> Self:
        if not isinstance(value, str) or not cls.pattern.fullmatch(value):
            msg = f"{cls.__name__} inválido: {value!r}"
            raise ValidationError(msg)
        return super().__new__(cls, value)


class AgentId(PatternId):
    """Agente declarado (6.2: ^[a-z][a-z0-9_-]{1,31}$)."""

    __slots__ = ()
    pattern = re.compile(r"^[a-z][a-z0-9_-]{1,31}$")


class PlanId(PatternId):
    """Plan local de un agente (6.2: pln_ + 12 caracteres)."""

    __slots__ = ()
    pattern = re.compile(r"^pln_[a-z0-9]{12}$")


class StepId(PatternId):
    """Paso de un QueryPlan (6.2: s1 a s99)."""

    __slots__ = ()
    pattern = re.compile(r"^s[0-9]{1,2}$")

    @property
    def number(self) -> int:
        """Número del paso, para ordenar s2 antes que s10."""
        return int(self[1:])


class CallId(PatternId):
    """Llamada MCP (6.4: cal_...)."""

    __slots__ = ()
    pattern = re.compile(r"^cal_[A-Za-z0-9]{1,60}$")


class CorrelationId(PatternId):
    """Identificador de correlación propagado (6.4: cor_...)."""

    __slots__ = ()
    pattern = re.compile(r"^cor_[A-Za-z0-9]{1,60}$")


class FactId(PatternId):
    """Clave de un hecho dentro del sobre de una llamada (6.2: máximo 64)."""

    __slots__ = ()


class PassageId(PatternId):
    """Pasaje documental dentro de una ejecución (6.9.2)."""

    __slots__ = ()


class MediaId(PatternId):
    """Adjunto referenciado dentro de una ejecución (6.9.2)."""

    __slots__ = ()


class ClaimId(PatternId):
    """Afirmación numérica de la respuesta narrada (6.3)."""

    __slots__ = ()
