"""Temas: tabla ⇄ dominio. El centroide lo calcula y escribe el agrupamiento, no este puerto."""

from sqlalchemy import RowMapping

from carmen.adapters.persistence.types import instant
from carmen.application.ports.repositories import Topic, TopicId, TopicStatus
from carmen.domain.system import SystemId


def topic_values(t: Topic) -> dict[str, object]:
    return {
        "id": str(t.topic_id),
        "label": t.label,
        "asked": t.asked,
        "resolved": t.resolved,
        "unresolved": t.unresolved,
        "systems": sorted(str(s) for s in t.systems),
        "status": t.status.value,
        "first_seen": t.first_seen.at,
        "last_seen": t.last_seen.at,
        "updated_at": t.last_seen.at,
    }


def topic_from_row(r: RowMapping) -> Topic:
    return Topic(
        topic_id=TopicId(r["id"]),
        label=r["label"],
        asked=int(r["asked"]),
        resolved=int(r["resolved"]),
        unresolved=int(r["unresolved"]),
        systems=frozenset(SystemId(s) for s in r["systems"]),
        status=TopicStatus(r["status"]),
        first_seen=instant(r["first_seen"]),
        last_seen=instant(r["last_seen"]),
    )
