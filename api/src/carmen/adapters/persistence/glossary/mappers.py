"""Glosario: tabla ⇄ dominio, y el término como JSON para el historial."""

from collections.abc import Mapping

from sqlalchemy import RowMapping

from carmen.adapters.persistence.types import as_mapping, as_sequence, dumps, instant, loads
from carmen.application.jsontypes import JsonValue
from carmen.application.ports.repositories import (
    GlossaryAction,
    GlossaryChange,
    GlossaryTerm,
    TermSource,
)
from carmen.domain.errors import ValidationError
from carmen.domain.ids import PrincipalId
from carmen.domain.time import Instant


def term_values(t: GlossaryTerm, actor: PrincipalId, at: Instant) -> dict[str, object]:
    return {
        "term": t.term,
        "display": t.display,
        "definition": t.definition,
        "aliases": list(t.aliases),
        "canonical": t.canonical,
        "active": t.active,
        "source": t.source.value,
        "created_by": str(actor),
        "created_at": at.at,
        "updated_by": str(actor),
        "updated_at": at.at,
    }


def term_from_row(r: RowMapping) -> GlossaryTerm:
    return GlossaryTerm(
        term=r["term"],
        display=r["display"],
        definition=r["definition"],
        aliases=tuple(r["aliases"]),
        canonical=bool(r["canonical"]),
        active=bool(r["active"]),
        source=TermSource(r["source"]),
    )


def term_to_json(t: GlossaryTerm | None) -> str | None:
    if t is None:
        return None
    return dumps(
        {
            "term": t.term,
            "display": t.display,
            "definition": t.definition,
            "aliases": list(t.aliases),
            "canonical": t.canonical,
            "active": t.active,
            "source": t.source.value,
        }
    )


def _field[T](data: Mapping[str, JsonValue], key: str, kind: type[T]) -> T:
    value = data.get(key)
    if not isinstance(value, kind):
        msg = f"{key} del historial del glosario debe ser {kind.__name__}"
        raise ValidationError(msg)
    return value


def term_from_json(text: str | None) -> GlossaryTerm | None:
    if text is None:
        return None
    data = as_mapping(loads(text))
    return GlossaryTerm(
        term=_field(data, "term", str),
        display=_field(data, "display", str),
        definition=_field(data, "definition", str),
        aliases=tuple(str(a) for a in as_sequence(data.get("aliases", []))),
        canonical=_field(data, "canonical", bool),
        active=_field(data, "active", bool),
        source=TermSource(_field(data, "source", str)),
    )


def history_row(c: GlossaryChange) -> dict[str, object]:
    return {
        "term": c.term,
        "action": c.action.value,
        "before": term_to_json(c.before),
        "after": term_to_json(c.after),
        "actor": str(c.actor),
        "at": c.at.at,
    }


def change_from_row(r: RowMapping) -> GlossaryChange:
    return GlossaryChange(
        term=r["term"],
        action=GlossaryAction(r["action"]),
        actor=PrincipalId(r["actor"]),
        at=instant(r["at"]),
        before=term_from_json(r["before"]),
        after=term_from_json(r["after"]),
    )
