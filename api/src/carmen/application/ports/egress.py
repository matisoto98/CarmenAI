"""Salida externa gobernada del ejecutor de agente (5.15.6).

Lo usa solo el ejecutor de un agente externo o híbrido; el supervisor no puede importarlo. Todo se
comprueba ANTES de abrir la conexión: dominio permitido, política, clasificación y presupuesto.
"""

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from carmen.application.context import ExecutionContext
from carmen.domain.egress.models import DataClass, Purpose
from carmen.domain.errors import ValidationError
from carmen.domain.ids import AgentId, PatternId
from carmen.domain.text import require_text
from carmen.domain.time import Instant


class Url(PatternId):
    """Solo HTTPS, sin credenciales en la URL."""

    __slots__ = ()
    pattern = re.compile(r"^https://[A-Za-z0-9.-]+(:[0-9]{1,5})?(/[^\s@]*)?$")

    @property
    def domain(self) -> str:
        return self.removeprefix("https://").split("/", 1)[0].split(":", 1)[0].lower()


@dataclass(frozen=True, slots=True)
class EgressOutcome:
    """El contenido recuperado es NO CONFIABLE: entra como pasaje con procedencia, jamás como
    instrucción.
    """

    url_final: Url
    domain: str
    fetched_at: Instant
    content: bytes | str
    redacted: tuple[str, ...]
    cost_eur: Decimal
    policy_id: str

    def __post_init__(self) -> None:
        require_text("policy_id", self.policy_id)
        if self.domain != self.url_final.domain:
            msg = "el dominio se revalida contra la URL final, tras las redirecciones"
            raise ValidationError(msg)
        if not self.cost_eur.is_finite() or self.cost_eur < 0:
            msg = "cost_eur debe ser >= 0"
            raise ValidationError(msg)


class EgressPort(Protocol):
    async def fetch(
        self,
        *,
        agent_id: AgentId,
        url: Url,
        purpose: Purpose,
        classification: DataClass,
        ctx: ExecutionContext,
    ) -> EgressOutcome:
        """Recupera un recurso externo a través de la pasarela.

        Lanza: EgressDomainNotAllowedError, EgressClassificationDeniedError,
        EgressBudgetExceededError, EgressUnavailableError.
        """
        ...
