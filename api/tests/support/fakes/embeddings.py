"""Embeddings deterministas: el mismo texto da siempre el mismo vector unitario."""

import hashlib
import math
from collections.abc import Mapping, Sequence

from carmen.application.errors import EmbeddingDimensionMismatchError
from carmen.application.ports.embeddings import Vector
from carmen.domain.errors import CarmenError

DIMENSION = 1024


def deterministic_vector(text: str, dimension: int = DIMENSION) -> Vector:
    """Vector unitario derivado de SHA-256 del texto. Sin aleatoriedad ni estado."""
    raw: list[float] = []
    counter = 0
    while len(raw) < dimension:
        digest = hashlib.sha256(f"{counter}:{text}".encode()).digest()
        raw.extend((byte - 127.5) / 127.5 for byte in digest)
        counter += 1
    values = raw[:dimension]
    norm = math.sqrt(sum(v * v for v in values))
    return tuple(v / norm for v in values)


class FakeEmbeddingAdapter:
    """Con `fixed`, los textos indicados reciben ese vector: así una prueba fija similitudes."""

    def __init__(
        self,
        *,
        dimension: int = DIMENSION,
        fixed: Mapping[str, Vector] | None = None,
        fail_with: CarmenError | None = None,
    ) -> None:
        self._dimension = dimension
        self._fixed = dict(fixed or {})
        self._fail_with = fail_with
        self.calls: list[tuple[str, ...]] = []

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed(self, texts: Sequence[str]) -> list[Vector]:
        self.calls.append(tuple(texts))
        if self._fail_with is not None:
            raise self._fail_with
        vectors = [self._fixed.get(t) or deterministic_vector(t, self._dimension) for t in texts]
        for vector in vectors:
            if len(vector) != self._dimension:
                msg = f"vector de {len(vector)} componentes; se esperaban {self._dimension}"
                raise EmbeddingDimensionMismatchError(msg)
        return vectors


def cosine(a: Vector, b: Vector) -> float:
    if len(a) != len(b):
        msg = "vectores de dimensión distinta"
        raise EmbeddingDimensionMismatchError(msg)
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return 0.0 if norm == 0 else dot / norm
