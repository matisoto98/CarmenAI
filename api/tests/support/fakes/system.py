"""Reloj, identificadores y eventos deterministas (5.5, 5.6)."""

from datetime import timedelta

from carmen.application.events import DomainEvent, EventType
from carmen.domain.time import Instant

EPOCH = Instant.parse("2026-07-27T09:14:20Z")


class FrozenClock:
    """Devuelve siempre el mismo instante, o avanza `tick` en cada lectura si se pide."""

    def __init__(self, start: Instant = EPOCH, tick: timedelta = timedelta(0)) -> None:
        if tick < timedelta(0):
            msg = "el reloj no retrocede"
            raise ValueError(msg)
        self._current = start
        self._tick = tick

    def now(self) -> Instant:
        current = self._current
        self._current = Instant(current.at + self._tick)
        return current

    def advance(self, delta: timedelta) -> None:
        if delta < timedelta(0):
            msg = "el reloj no retrocede"
            raise ValueError(msg)
        self._current = Instant(self._current.at + delta)


class SeqIdGenerator:
    """000000000001, 000000000002… Válido detrás de cualquier prefijo del dominio."""

    def __init__(self, start: int = 1) -> None:
        if start < 1:
            msg = "la secuencia empieza en 1 o más"
            raise ValueError(msg)
        self._next = start

    def new_id(self) -> str:
        value = f"{self._next:012d}"
        self._next += 1
        return value


class ListEventSink:
    """Guarda los eventos en orden. Con `broken`, los pierde sin lanzar, como exige el puerto."""

    def __init__(self, *, broken: bool = False) -> None:
        self.events: list[DomainEvent] = []
        self.dropped: list[DomainEvent] = []
        self._broken = broken

    async def emit(self, event: DomainEvent) -> None:
        (self.dropped if self._broken else self.events).append(event)

    def types(self) -> list[EventType]:
        return [e.event_type for e in self.events]
