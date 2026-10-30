"""Modelo de lenguaje con guion: devuelve, en orden, lo que la prueba le da."""

from collections import deque
from collections.abc import AsyncIterator, Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal

from carmen.application.errors import LlmMalformedOutputError
from carmen.application.jsontypes import JsonObject
from carmen.application.ports.llm import (
    LlmDescriptor,
    LlmMessage,
    LlmStructuredResult,
    LlmTextChunk,
    RequestId,
    ToolSpec,
)
from carmen.domain.conversation.turn import TokenUsage
from carmen.domain.errors import CarmenError, LlmUnavailableError

FAKE_DESCRIPTOR = LlmDescriptor(
    provider="fake",
    model="fake-llm",
    revision="2026-07-01",
    temperature=Decimal(0),
    config_hash="cfg_fake",
)


@dataclass(frozen=True, slots=True)
class LlmCall:
    request_id: RequestId
    messages: tuple[LlmMessage, ...]
    tools: tuple[ToolSpec, ...] | None = None
    response_schema: JsonObject | None = None


class FakeLlmAdapter:
    """Sin guion pendiente, lanza LlmUnavailableError: una prueba nunca recibe una respuesta
    que no escribió.
    """

    def __init__(
        self,
        *,
        structured: Iterable[LlmStructuredResult | CarmenError] = (),
        streams: Iterable[Sequence[str] | CarmenError] = (),
        descriptor: LlmDescriptor = FAKE_DESCRIPTOR,
    ) -> None:
        self._structured = deque(structured)
        self._streams = deque(streams)
        self._descriptor = descriptor
        self.calls: list[LlmCall] = []

    async def complete_structured(
        self,
        *,
        messages: Sequence[LlmMessage],
        tools: Sequence[ToolSpec] | None,
        response_schema: JsonObject | None,
        request_id: RequestId,
    ) -> LlmStructuredResult:
        self.calls.append(
            LlmCall(
                request_id,
                tuple(messages),
                None if tools is None else tuple(tools),
                response_schema,
            )
        )
        if not self._structured:
            msg = "FakeLlmAdapter sin respuesta estructurada en el guion"
            raise LlmUnavailableError(msg)
        item = self._structured.popleft()
        if isinstance(item, CarmenError):
            raise item
        if response_schema is not None and item.structured is None:
            msg = "se pidió un objeto estructurado y el guion no lo trae"
            raise LlmMalformedOutputError(msg)
        return item

    async def stream_text(
        self, *, messages: Sequence[LlmMessage], request_id: RequestId
    ) -> AsyncIterator[LlmTextChunk]:
        self.calls.append(LlmCall(request_id, tuple(messages)))
        if not self._streams:
            msg = "FakeLlmAdapter sin texto en el guion"
            raise LlmUnavailableError(msg)
        item = self._streams.popleft()
        if isinstance(item, CarmenError):
            raise item
        last = len(item) - 1
        for index, text in enumerate(item):
            final = index == last
            tokens = TokenUsage(tokens_in=len(messages), tokens_out=len(item)) if final else None
            yield LlmTextChunk(index=index, text=text, final=final, tokens=tokens)

    def descriptor(self) -> LlmDescriptor:
        return self._descriptor

    @property
    def pending(self) -> int:
        return len(self._structured) + len(self._streams)
