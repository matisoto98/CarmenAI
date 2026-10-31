"""Salida externa que lo deniega todo: el valor por defecto de la política es deny (7.10.2)."""

from dataclasses import dataclass

from carmen.application.context import ExecutionContext
from carmen.application.errors import EgressDomainNotAllowedError
from carmen.application.ports.egress import EgressOutcome, Url
from carmen.domain.egress.models import DataClass, Purpose
from carmen.domain.ids import AgentId


@dataclass(frozen=True, slots=True)
class EgressAttempt:
    agent_id: AgentId
    url: Url
    purpose: Purpose
    classification: DataClass


class FakeEgress:
    """Registra el intento y lo rechaza antes de abrir ninguna conexión."""

    def __init__(self) -> None:
        self.attempts: list[EgressAttempt] = []

    async def fetch(
        self,
        *,
        agent_id: AgentId,
        url: Url,
        purpose: Purpose,
        classification: DataClass,
        ctx: ExecutionContext,
    ) -> EgressOutcome:
        self.attempts.append(EgressAttempt(agent_id, url, purpose, classification))
        msg = f"{url.domain} no está en ninguna allowlist: sin política, deny"
        raise EgressDomainNotAllowedError(msg)
