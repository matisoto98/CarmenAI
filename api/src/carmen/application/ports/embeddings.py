"""Embeddings del supervisor: memoria de planes, lagunas, corpus y temas (5.5)."""

from collections.abc import Sequence
from typing import Protocol

Vector = tuple[float, ...]


class EmbeddingPort(Protocol):
    @property
    def dimension(self) -> int:
        """FIJA (corrección C2): se valida al arrancar contra las columnas vector(1024)."""
        ...

    async def embed(self, texts: Sequence[str]) -> list[Vector]:
        """Un vector por texto, en el mismo orden y todos de `dimension` componentes.

        Lanza: EmbeddingUnavailableError, EmbeddingTimeoutError, EmbeddingDimensionMismatchError.
        """
        ...
