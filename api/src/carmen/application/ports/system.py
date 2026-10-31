"""Reloj, identificadores y eventos: lo que hace deterministas las pruebas (5.5, 5.6)."""

from typing import Protocol

from carmen.application.events import DomainEvent
from carmen.domain.time import Instant


class Clock(Protocol):
    def now(self) -> Instant:
        """Síncrono a propósito. Ningún módulo lee la hora del sistema por su cuenta."""
        ...


class IdGenerator(Protocol):
    def new_id(self) -> str:
        """Doce caracteres en minúscula y dígitos. Quien lo usa le pone su prefijo (trn_, run_…)."""
        ...


class EventSink(Protocol):
    async def emit(self, event: DomainEvent) -> None:
        """No lanza: un fallo de emisión NUNCA aborta la ejecución. Se registra y se continúa."""
        ...
