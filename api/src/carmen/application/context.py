"""Contexto de ejecución: se crea en presentación y se PASA explícitamente hacia abajo (6.7).

No hay variables de contexto implícitas ni estado global. El token del usuario viaja dentro, pero
no se imprime: un repr o un log nunca lo muestran, y el agente lo cambia por uno delegado (7.8.1).
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from carmen.application.ports.llm import LlmDescriptor
from carmen.domain.errors import ValidationError
from carmen.domain.ids import ConversationId, CorrelationId, MessageId, PrincipalId
from carmen.domain.locale import Locale
from carmen.domain.role import Role
from carmen.domain.system import SystemId
from carmen.domain.text import require_text
from carmen.domain.time import Instant


@dataclass(frozen=True, slots=True)
class UserToken:
    """Token de Entra ID del usuario. Opaco: solo lo lee el intercambio delegado."""

    value: str = field(repr=False)

    def __post_init__(self) -> None:
        require_text("token", self.value)

    def __str__(self) -> str:
        return "UserToken(***)"


@dataclass(frozen=True, slots=True)
class Requester:
    """Quién pregunta: identificador saneado, rol de plataforma y token."""

    principal_id: PrincipalId
    role: Role
    token: UserToken


@dataclass(frozen=True, slots=True)
class ExecutionContext:
    correlation_id: CorrelationId
    conversation_id: ConversationId
    message_id: MessageId
    requester: Requester
    locale: Locale
    started_at: Instant
    llm: LlmDescriptor
    prompt_hash: str
    catalog_versions: Mapping[SystemId, str]
    deadline: Instant | None = None

    def __post_init__(self) -> None:
        require_text("prompt_hash", self.prompt_hash)
        if self.deadline is not None and self.deadline <= self.started_at:
            msg = "el plazo del turno debe ser posterior a su inicio"
            raise ValidationError(msg)
        object.__setattr__(self, "catalog_versions", MappingProxyType(dict(self.catalog_versions)))

    def expired(self, now: Instant) -> bool:
        return self.deadline is not None and now >= self.deadline
