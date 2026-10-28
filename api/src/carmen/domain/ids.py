"""Identificadores tipados del dominio.

Cada identificador es un str inmutable que valida su forma al construirse, de modo que un
PlanId no se confunde con un CallId ni en el tipado ni en tiempo de ejecución.
"""

import re
from typing import ClassVar, Final, Self

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
    """Agente declarado, con el prefijo de 5.14.3 y 7.9.6: agent.vigia (ADR-044)."""

    __slots__ = ()
    pattern = re.compile(r"^agent\.[a-z][a-z0-9_-]{1,31}$")


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


# --- Orquestación y gobierno (Prompt 3, 6.12 y 7.9) ---


class TaskId(PatternId):
    """Tarea de un DelegationPlan (6.12.3: t1, t2…)."""

    __slots__ = ()
    pattern = re.compile(r"^t[0-9]{1,2}$")

    @property
    def number(self) -> int:
        return int(self[1:])


class DelegationPlanId(PatternId):
    """Plan global del supervisor (6.12.3: dpl_ + 12 caracteres)."""

    __slots__ = ()
    pattern = re.compile(r"^dpl_[a-z0-9]{12}$")


class TurnId(PatternId):
    """Turno de conversación (6.12.3: trn_...)."""

    __slots__ = ()
    pattern = re.compile(r"^trn_[a-z0-9]{4,32}$")


class ConversationId(PatternId):
    """Conversación que agrupa turnos."""

    __slots__ = ()
    pattern = re.compile(r"^cnv_[a-z0-9]{4,32}$")


class PrincipalId(PatternId):
    """Principal pseudonimizado (6.12.3: usr_...)."""

    __slots__ = ()
    pattern = re.compile(r"^usr_[a-z0-9]{4,32}$")


class RunId(PatternId):
    """Ejecución de un agente sobre una tarea."""

    __slots__ = ()
    pattern = re.compile(r"^run_[a-z0-9]{4,32}$")


class ApprovalId(PatternId):
    """Petición de aprobación humana (6.12.6)."""

    __slots__ = ()
    pattern = re.compile(r"^apr_[a-z0-9]{4,32}$")


_DOTTED: Final = r"[a-z][a-z0-9_-]*(\.[a-z][a-z0-9_-]*)*"


class RoleId(PatternId):
    """Rol de la política (7.9.6: ops.operator, carmen.admin)."""

    __slots__ = ()
    pattern = re.compile(rf"^{_DOTTED}$")


class Scope(PatternId):
    """Alcance que concede un rol sobre un agente (7.9.6: vigia.read.limited)."""

    __slots__ = ()
    pattern = re.compile(rf"^{_DOTTED}$")


class ProviderId(PatternId):
    """Proveedor de modelo registrado (5.15.4: provider.internal-ollama)."""

    __slots__ = ()
    pattern = re.compile(r"^provider\.[a-z][a-z0-9_-]{1,47}$")


class McpServerId(PatternId):
    """Servidor MCP ligado a un agente (5.14.3: mcp.vigia-ops)."""

    __slots__ = ()
    pattern = re.compile(r"^mcp\.[a-z][a-z0-9_-]{1,47}$")


class DelegatedIdentityRef(PatternId):
    """Referencia resoluble a la identidad delegada del usuario, NUNCA el token (6.12.9).

    El patrón no admite puntos ni espacios, así que un JWT o un «Bearer ...» no caben.
    """

    __slots__ = ()
    pattern = re.compile(r"^idr_[A-Za-z0-9]{8,64}$")
