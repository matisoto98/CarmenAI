"""Proveedor de modelo simulado con bindings por agente (7.10.1)."""

from collections.abc import Mapping
from decimal import Decimal

from carmen.application.context import ExecutionContext
from carmen.application.errors import ClassificationDeniedError, ProviderNotBoundError
from carmen.application.ports.model_provider import ModelPayload
from carmen.application.ports.system import Clock
from carmen.domain.egress.models import DataClass
from carmen.domain.ids import AgentId, ProviderId
from carmen.domain.model_output import ModelOutput
from support.fakes.system import FrozenClock


class FakeModelProvider:
    """`bindings` dice, por (agente, proveedor), la clase de dato más alta que puede salir."""

    def __init__(
        self,
        *,
        bindings: Mapping[tuple[AgentId, ProviderId], DataClass],
        text: str = "salida simulada del proveedor",
        clock: Clock | None = None,
    ) -> None:
        self._bindings = dict(bindings)
        self._text = text
        self._clock = clock or FrozenClock()
        self.payloads: list[ModelPayload] = []

    async def complete(
        self,
        *,
        agent_id: AgentId,
        provider: ProviderId,
        payload: ModelPayload,
        classification: DataClass,
        ctx: ExecutionContext,
    ) -> ModelOutput:
        ceiling = self._bindings.get((agent_id, provider))
        if ceiling is None:
            msg = f"{provider} no está ligado a {agent_id}"
            raise ProviderNotBoundError(msg)
        if not classification.fits_within(ceiling):
            msg = f"{classification} supera {ceiling} para {provider}"
            raise ClassificationDeniedError(msg)
        self.payloads.append(payload)
        return ModelOutput(
            provider=provider,
            model=payload.model,
            model_version="sim-1",
            purpose=payload.purpose,
            text=self._text,
            tokens_in=sum(len(m.content.split()) for m in payload.messages),
            tokens_out=len(self._text.split()),
            cost_eur=Decimal(0),
            produced_at=self._clock.now(),
        )
