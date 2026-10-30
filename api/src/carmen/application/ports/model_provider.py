"""Proveedores de modelo registrados y ligados a un agente (5.15.6, 7.10.1).

Lo usa solo el ejecutor de un agente externo o híbrido; el supervisor no puede importarlo.
"""

from dataclasses import dataclass
from typing import Protocol

from carmen.application.context import ExecutionContext
from carmen.application.ports.llm import LlmMessage
from carmen.domain.egress.models import DataClass, Purpose
from carmen.domain.errors import ValidationError
from carmen.domain.ids import AgentId, ProviderId
from carmen.domain.model_output import ModelOutput
from carmen.domain.text import require_text


@dataclass(frozen=True, slots=True)
class ModelPayload:
    """Lo que sale hacia el proveedor: ya redactado y reducido a lo imprescindible."""

    model: str
    purpose: Purpose
    messages: tuple[LlmMessage, ...]
    max_tokens: int

    def __post_init__(self) -> None:
        require_text("model", self.model)
        if not self.messages:
            msg = "una llamada a un proveedor lleva al menos un mensaje"
            raise ValidationError(msg)
        if isinstance(self.max_tokens, bool) or self.max_tokens < 1:
            msg = f"max_tokens debe ser >= 1: {self.max_tokens!r}"
            raise ValidationError(msg)


class ModelProviderPort(Protocol):
    async def complete(
        self,
        *,
        agent_id: AgentId,
        provider: ProviderId,
        payload: ModelPayload,
        classification: DataClass,
        ctx: ExecutionContext,
    ) -> ModelOutput:
        """Llama a un proveedor REGISTRADO y ligado a ese agente. Devuelve ModelOutput, NUNCA
        evidencia.

        Lanza: ProviderNotBoundError, ClassificationDeniedError, BudgetExceededError.
        """
        ...
