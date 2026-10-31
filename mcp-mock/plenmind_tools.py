"""Herramientas del sistema documental simulado (plenmind), sobre documents.py (6.9.4).

Las documentales devuelven passages o media y nunca facts. Cada pasaje lleva documento, sección,
ancla, versión, fecha, enlace y relevancia. La media viaja como referencia autenticada al propio
simulado, nunca en base64. query_metric es la excepción del catálogo: cifras de uso del propio
sistema documental, agregadas sobre un registro de consultas generado con la semilla.
"""

import random
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import cache
from typing import Final

from documents import (
    DOCUMENTS,
    GLOSSARY_DOCUMENT,
    GLOSSARY_UPDATED,
    GLOSSARY_VERSION,
    Document,
    Passage,
    definition,
    document,
    figure,
    png,
    tokens,
)
from envelope import Answer, Json
from mock_errors import ToolError
from periods import interpret
from vigia_tools import fact

SEARCH_LIMIT: Final = 8
LOG_DAYS: Final = 430
_LOG_SALT: Final = 0x5EED


@dataclass(frozen=True, slots=True)
class DocCall:
    args: dict[str, Json]
    answer: Answer
    base_url: str
    now: datetime
    seed: int

    def text(self, name: str) -> str | None:
        value = self.args.get(name)
        return None if value is None else str(value)


def passage_json(
    call: DocCall, doc: Document, p: Passage, relevance: float = 1.0
) -> dict[str, Json]:
    return {
        "passage_id": f"{doc.document_id}:{p.key}",
        "document_id": doc.document_id,
        "title": doc.title,
        "section": p.section,
        "anchor": p.anchor,
        "text": p.text,
        "kind": p.kind,
        "doc_version": doc.version,
        "updated_at": doc.updated_at,
        "url": f"{call.base_url}/doc/{doc.document_id}#{p.anchor.replace(' ', '')}",
        "relevance": round(relevance, 2),
    }


def media_json(call: DocCall, media_id: str) -> dict[str, Json] | None:
    found = figure(media_id)
    if found is None:
        return None
    doc, fig = found
    return {
        "media_id": fig.media_id,
        "document_id": doc.document_id,
        "mime": "image/png",
        "caption": fig.caption,
        "uri": f"{call.base_url}/media/{doc.document_id}/{fig.figure}",
        "bytes": len(png(fig.figure)),
        "anchor": fig.anchor,
    }


def _not_found(call: DocCall, document_id: str) -> None:
    call.answer.warn("documento_no_encontrado", f"no hay ningún documento {document_id}")


def _best_runbook(problem: str) -> Document | None:
    wanted = tokens(problem)
    scored = [
        (len(wanted & tokens(f"{d.title} {d.equipo}")), d.document_id, d)
        for d in DOCUMENTS
        if d.is_runbook
    ]
    scored = [s for s in scored if s[0] > 0]
    if not scored:
        return None
    return sorted(scored, key=lambda s: (-s[0], s[1]))[0][2]


# --- Herramientas ----------------------------------------------------------------------------


def search_documents(call: DocCall) -> None:
    wanted = tokens(str(call.args["query"]))
    tipo, area = call.text("tipo"), call.text("area")
    only_current = call.args.get("solo_vigentes") is True
    hits: list[tuple[float, str, Document, Passage]] = []
    for doc in DOCUMENTS:
        if (
            (tipo and doc.tipo != tipo)
            or (area and doc.area != area)
            or (only_current and not doc.vigente)
        ):
            continue
        for p in doc.passages:
            found = wanted & tokens(f"{doc.title} {p.section} {p.text}")
            if found:
                relevance = min(1.0, len(found) / max(len(wanted), 1))
                hits.append((relevance, f"{doc.document_id}:{p.key}", doc, p))
    hits.sort(key=lambda h: (-h[0], h[1]))
    call.answer.passages = [passage_json(call, d, p, r) for r, _, d, p in hits[:SEARCH_LIMIT]]
    if not hits:
        call.answer.warn("sin_resultados", "ningún documento responde a la búsqueda")


def get_document_section(call: DocCall) -> None:
    document_id, section = str(call.args["document_id"]), str(call.args["section"])
    doc = document(document_id)
    if doc is None:
        _not_found(call, document_id)
        return
    chosen = [p for p in doc.passages if p.section.startswith(section) or p.key == section]
    if not chosen:
        call.answer.warn("seccion_no_encontrada", f"{document_id} no tiene la sección {section}")
    call.answer.passages = [passage_json(call, doc, p) for p in chosen]


def get_procedure(call: DocCall) -> None:
    document_id, problem = call.text("document_id"), call.text("problema")
    if document_id is None and problem is None:
        msg = "get_procedure necesita document_id o problema"
        raise ToolError(msg)
    doc = document(document_id) if document_id is not None else _best_runbook(problem or "")
    if doc is None or not doc.is_runbook:
        _not_found(call, document_id or f"para «{problem}»")
        return
    if not doc.vigente:
        call.answer.warn(
            "documento_no_vigente",
            f"{doc.document_id} v{doc.version} es de {doc.updated_at[:10]} y no está en vigor",
        )
    steps = [p for p in doc.passages if p.kind in ("warning", "procedure")]
    call.answer.passages = [passage_json(call, doc, p) for p in steps]
    call.answer.media = [m for f in doc.figures if (m := media_json(call, f.media_id))]


def list_procedures(call: DocCall) -> None:
    wanted = tokens(f"{call.text('problema') or ''} {call.text('equipo') or ''}")
    for doc in DOCUMENTS:
        if not doc.is_runbook:
            continue
        found = wanted & tokens(f"{doc.title} {doc.equipo}")
        if wanted and not found:
            continue
        call.answer.passages.append(
            {
                "passage_id": f"{doc.document_id}:indice",
                "document_id": doc.document_id,
                "title": doc.title,
                "section": "Índice de procedimientos",
                "text": (
                    f"{doc.document_id} · {doc.title} (v{doc.version}, {doc.updated_at[:10]}). "
                    f"Equipo: {doc.equipo}."
                ),
                "kind": "reference",
                "doc_version": doc.version,
                "updated_at": doc.updated_at,
                "url": f"{call.base_url}/doc/{doc.document_id}",
                "relevance": round(len(found) / len(wanted), 2) if wanted else 1.0,
            }
        )
    call.answer.passages.sort(key=lambda p: (-float(str(p["relevance"])), str(p["passage_id"])))
    if not call.answer.passages:
        call.answer.warn("sin_resultados", "no hay procedimientos para ese problema o equipo")


def get_media(call: DocCall) -> None:
    media_id = str(call.args["media_id"])
    item = media_json(call, media_id)
    if item is None:
        call.answer.warn("media_no_encontrada", f"no hay ningún recurso {media_id}")
        return
    call.answer.media = [item]


def glossary(call: DocCall) -> None:
    term = str(call.args["term"])
    entry = definition(term)
    if entry is None:
        call.answer.warn("termino_no_encontrado", f"«{term}» no está en el glosario")
        return
    call.answer.passages = [
        {
            "passage_id": f"{GLOSSARY_DOCUMENT}:{entry.term.replace(' ', '_')}",
            "document_id": GLOSSARY_DOCUMENT,
            "title": "Glosario de operación",
            "section": entry.term,
            "text": entry.text,
            "kind": "definition",
            "doc_version": GLOSSARY_VERSION,
            "updated_at": GLOSSARY_UPDATED,
            "url": f"{call.base_url}/doc/{GLOSSARY_DOCUMENT}#{entry.term.replace(' ', '-')}",
            "relevance": 1.0,
        }
    ]


@cache
def _usage_log(seed: int, now: datetime) -> tuple[tuple[datetime, int, int], ...]:
    """Por día: (inicio, consultas, minutos sin servicio). Generado, nunca escrito a mano."""
    rng = random.Random(seed ^ _LOG_SALT)
    start = (now - timedelta(days=LOG_DAYS)).replace(hour=0, minute=0, second=0)
    days = []
    day = start
    while day < now:
        days.append((day, rng.randint(20, 90), rng.choice((0, 0, 0, 0, 5, 12, 30))))
        day += timedelta(days=1)
    return tuple(days)


def query_metric(call: DocCall) -> None:
    metric = str(call.args["metric"])
    period = interpret(str(call.args["period"]), call.now)
    call.answer.period = period
    log = _usage_log(call.seed, call.now)
    if period.instant:
        chosen = [d for d in log if d[0] <= period.end < d[0] + timedelta(days=1)]
    else:
        chosen = [d for d in log if period.start <= d[0] + timedelta(days=1) and d[0] < period.end]
    if metric == "consultas":
        call.answer.facts = [
            fact(
                "consultas",
                "Consultas al corpus",
                sum(d[1] for d in chosen),
                "count",
                metric="consultas",
            )
        ]
        return
    minutes = len(chosen) * 24 * 60
    down = sum(d[2] for d in chosen)
    value = round(100 * (minutes - down) / minutes, 2) if minutes else 100.0
    call.answer.facts = [
        fact(
            "disponibilidad",
            "Disponibilidad del servicio documental",
            value,
            "percent",
            metric="disponibilidad",
        )
    ]


TOOLS: Final[dict[str, Callable[[DocCall], None]]] = {
    "search_documents": search_documents,
    "get_document_section": get_document_section,
    "get_procedure": get_procedure,
    "list_procedures": list_procedures,
    "get_media": get_media,
    "glossary": glossary,
    "query_metric": query_metric,
}
