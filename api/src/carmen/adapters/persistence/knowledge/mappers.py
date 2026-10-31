"""Corpus organizativo: tabla ⇄ dominio."""

from dataclasses import dataclass

from sqlalchemy import RowMapping

from carmen.adapters.persistence.types import vector_value
from carmen.application.ports.embeddings import Vector
from carmen.application.ports.repositories import KnowledgeChunk
from carmen.domain.text import require_non_negative, require_text
from carmen.domain.time import Instant


@dataclass(frozen=True, slots=True)
class KnowledgeChunkDraft:
    """Un fragmento por (source, chunk_ix): reingestar el mismo lo sustituye."""

    source: str
    chunk_ix: int
    title: str
    content: str
    embedding: Vector

    def __post_init__(self) -> None:
        require_text("source", self.source)
        require_text("title", self.title)
        require_text("content", self.content)
        require_non_negative("chunk_ix", self.chunk_ix)


def chunk_row(c: KnowledgeChunkDraft, now: Instant) -> dict[str, object]:
    return {
        "source": c.source,
        "title": c.title,
        "chunk_ix": c.chunk_ix,
        "content": c.content,
        "embedding": vector_value(c.embedding),
        "created_at": now.at,
        "updated_at": now.at,
    }


def chunk_from_row(r: RowMapping) -> KnowledgeChunk:
    return KnowledgeChunk(
        source=r["source"],
        chunk_ix=int(r["chunk_ix"]),
        title=r["title"],
        content=r["content"],
        similarity=float(r["similarity"]),
    )
