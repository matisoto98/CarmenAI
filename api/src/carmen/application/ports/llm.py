"""Modelo de lenguaje del supervisor y del agente (5.5).

El puerto devuelve texto y llamadas ya deserializadas; nunca evidencia. Lo que dice un modelo es
un ModelOutput aparte del resultado (6.12.4).
"""

import re
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import Final, Protocol

from carmen.application.jsontypes import JsonObject, JsonValue
from carmen.domain.conversation.turn import TokenUsage
from carmen.domain.errors import ValidationError
from carmen.domain.ids import PatternId
from carmen.domain.text import require_text

_TOOL_NAME: Final = re.compile(r"^[a-z][a-z0-9_]{1,47}$")


class RequestId(PatternId):
    """Una petición al modelo, para correlacionar trazas y reintentos."""

    __slots__ = ()
    pattern = re.compile(r"^req_[A-Za-z0-9]{4,60}$")


class LlmRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass(frozen=True, slots=True)
class LlmMessage:
    role: LlmRole
    content: str
    tool_call_id: str | None = None

    def __post_init__(self) -> None:
        if (self.role is LlmRole.TOOL) is (self.tool_call_id is None):
            msg = "tool_call_id va solo, y siempre, en los mensajes de rol tool"
            raise ValidationError(msg)


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """Una herramienta que el modelo puede pedir, con el esquema de sus argumentos."""

    name: str
    description: str
    parameters: JsonObject

    def __post_init__(self) -> None:
        if not _TOOL_NAME.fullmatch(self.name):
            msg = f"nombre de herramienta inválido: {self.name!r}"
            raise ValidationError(msg)
        require_text("description", self.description)


@dataclass(frozen=True, slots=True)
class LlmToolCall:
    call_ref: str
    name: str
    arguments: Mapping[str, JsonValue]

    def __post_init__(self) -> None:
        require_text("call_ref", self.call_ref)
        require_text("name", self.name)
        object.__setattr__(self, "arguments", MappingProxyType(dict(self.arguments)))


@dataclass(frozen=True, slots=True)
class LlmStructuredResult:
    text: str | None
    tool_calls: tuple[LlmToolCall, ...]
    tokens: TokenUsage
    structured: JsonObject | None = None

    def __post_init__(self) -> None:
        if self.text is None and not self.tool_calls and self.structured is None:
            msg = "un resultado del modelo trae texto, llamadas o un objeto estructurado"
            raise ValidationError(msg)


@dataclass(frozen=True, slots=True)
class LlmTextChunk:
    index: int
    text: str
    final: bool = False
    tokens: TokenUsage | None = None

    def __post_init__(self) -> None:
        if isinstance(self.index, bool) or self.index < 0:
            msg = f"index debe ser >= 0: {self.index!r}"
            raise ValidationError(msg)
        if self.tokens is not None and not self.final:
            msg = "el consumo de tokens solo llega en el último fragmento"
            raise ValidationError(msg)


@dataclass(frozen=True, slots=True)
class LlmDescriptor:
    """Modelo, revisión, temperatura efectiva y hash de configuración: metadato inmutable."""

    provider: str
    model: str
    revision: str
    temperature: Decimal
    config_hash: str

    def __post_init__(self) -> None:
        for name in ("provider", "model", "revision", "config_hash"):
            require_text(name, getattr(self, name))
        if not self.temperature.is_finite() or not Decimal(0) <= self.temperature <= Decimal(2):
            msg = f"temperatura fuera de [0, 2]: {self.temperature}"
            raise ValidationError(msg)


class LlmPort(Protocol):
    async def complete_structured(
        self,
        *,
        messages: Sequence[LlmMessage],
        tools: Sequence[ToolSpec] | None,
        response_schema: JsonObject | None,
        request_id: RequestId,
    ) -> LlmStructuredResult:
        """Devuelve texto y/o llamadas a herramienta ya deserializadas.

        Lanza: LlmUnavailableError, LlmTimeoutError, LlmMalformedOutputError.
        """
        ...

    def stream_text(
        self, *, messages: Sequence[LlmMessage], request_id: RequestId
    ) -> AsyncIterator[LlmTextChunk]:
        """Generador asíncrono de fragmentos; el último lleva final=True y los tokens.

        Lanza: LlmUnavailableError, LlmTimeoutError.
        """
        ...

    def descriptor(self) -> LlmDescriptor:
        """Síncrono: es metadato inmutable resuelto al construir."""
        ...
