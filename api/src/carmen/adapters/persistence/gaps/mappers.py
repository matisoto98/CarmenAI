"""Lagunas: tabla ⇄ dominio."""

from sqlalchemy import RowMapping

from carmen.adapters.persistence.types import instant, vector_value
from carmen.application.ports.repositories import GapCluster, GapDraft, GapId, GapStatus
from carmen.domain.locale import Locale


def gap_row(gap_id: GapId, g: GapDraft) -> dict[str, object]:
    return {
        "id": str(gap_id),
        "question_norm": g.question_norm,
        "question": g.question,
        "embedding": vector_value(g.embedding),
        "locale": g.locale.value,
        "reason": g.reason,
        "occurrences": 1,
        "status": GapStatus.OPEN.value,
        "first_seen": g.at.at,
        "last_seen": g.at.at,
    }


def cluster_from_row(r: RowMapping) -> GapCluster:
    return GapCluster(
        cluster_name=r["cluster_name"],
        locale=Locale(r["locale"]),
        questions=tuple(r["questions"]),
        occurrences=int(r["occurrences"]),
        last_seen=instant(r["last_seen"]),
    )
