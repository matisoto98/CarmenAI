"""Herramientas del sistema de métricas simulado (vigia), sobre dataset.py.

Toda cifra se agrega en el momento sobre las alarmas, monitores y sedes generados con la semilla:
ninguna está escrita a mano. Los avisos obligatorios de 5.16.1.1 salen con sus cifras: alarmas
abiertas acumuladas, rankings dominados por «Error de impresora», sedes degradadas infladas y,
para un OPERATOR, el ámbito de su zona.
"""

from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

from dataset import (
    CARWASH_FAULT,
    DEGRADED_OPEN_ALARMS,
    NEVER_CLOSED,
    OUTAGE,
    Alarm,
    Dataset,
    Site,
    normalize,
)
from envelope import Answer, Json
from identity import Principal
from mock_errors import InvalidParamsError, ToolError
from periods import Period, interpret, iso

PRINTER: Final = "Error de impresora"
PRINTER_SHARE_WARNING: Final = 0.25
CORRELATION_MINUTES: Final = 15
STEPS: Final = {"hora": timedelta(hours=1), "dia": timedelta(days=1), "semana": timedelta(days=7)}
WINDOWS: Final = {"24h": timedelta(hours=24), "7d": timedelta(days=7), "30d": timedelta(days=30)}
SNAPSHOT: Final = frozenset({"monitores_ko", "estado_monitores", "lavaderos", "lavaderos_ok"})
LABELS: Final = {
    "monitores_ko": "Monitores en KO",
    "alarmas": "Alarmas del periodo",
    "alarmas_abiertas": "Alarmas abiertas",
    "disponibilidad": "Disponibilidad",
    "sedes_degradadas": "Sedes degradadas",
    "lavaderos": "Lavaderos (universo)",
    "lavaderos_ok": "Lavaderos OK (sin avería abierta)",
}
#: Sustituciones que cuestan medio punto: confusiones fonéticas habituales en castellano.
_CLOSE_LETTERS: Final = frozenset(
    {frozenset(p) for p in ("rl", "bv", "sz", "cz", "gj", "yi", "ck", "mn")}
)
_EXACT_COST: Final = 0.5
_APPROX_SHARE: Final = 0.25


@dataclass(frozen=True, slots=True)
class Call:
    data: Dataset
    principal: Principal
    args: dict[str, Json]
    answer: Answer

    def text(self, name: str, default: str | None = None) -> str | None:
        value = self.args.get(name, default)
        return None if value is None else str(value)

    def period(self) -> Period:
        period = interpret(str(self.args["period"]), self.data.now)
        self.answer.period = period
        return period

    def scope(self) -> tuple[Site, ...]:
        """Sedes que el rol puede ver; un OPERATOR solo las de su zona, y se avisa."""
        sites = self.principal.visible_sites(self.data)
        if self.principal.zone is not None:
            self.answer.warn(
                "ambito_zona",
                f"cifras de la zona {self.principal.zone}: {len(sites)} de "
                f"{len(self.data.sites)} sedes",
            )
        return sites

    def site(self, raw: Json) -> Site:
        if isinstance(raw, dict) or raw is None:
            msg = "site_id debe llegar resuelto: una referencia a un hecho se resuelve antes"
            raise InvalidParamsError(msg)
        site = self.data.site(str(raw))
        if site is None:
            msg = f"sede desconocida: {raw}"
            raise ToolError(msg)
        self.principal.require_site(site)
        return site


# --- Agregados -------------------------------------------------------------------------------


def entity(site: Site) -> dict[str, Json]:
    return {"type": "site", "id": site.id, "name": site.name}


def fact(
    key: str,
    label: str,
    value: Json,
    unit: str | None,
    *,
    metric: str | None = None,
    site: Site | None = None,
    dimensions: dict[str, Json] | None = None,
) -> dict[str, Json]:
    item: dict[str, Json] = {"key": key, "label": label, "value": value}
    if unit is not None:
        item["unit"] = unit
    if metric is not None:
        item["metric"] = metric
    if site is not None:
        item["entity"] = entity(site)
    item["dimensions"] = dimensions or {}
    return item


def raised(alarms: Iterable[Alarm], period: Period, estado: str | None) -> list[Alarm]:
    """Alarmas abiertas dentro del periodo; en un instante, las abiertas en ese instante."""
    if period.instant:
        chosen = [a for a in alarms if a.open_at(period.end)]
    else:
        chosen = [a for a in alarms if period.start <= a.opened < period.end]
    if estado == "abierta":
        return [a for a in chosen if a.open_at(period.end)]
    if estado == "cerrada":
        return [a for a in chosen if a.closed is not None and a.closed <= period.end]
    return chosen


def open_at(alarms: Iterable[Alarm], at: datetime) -> list[Alarm]:
    return [a for a in alarms if a.open_at(at)]


def availability(data: Dataset, sites: Sequence[Site], period: Period) -> float:
    """Media por sede del tiempo sin «Surtidor sin comunicación» dentro del periodo."""
    if not sites:
        return 0.0
    outages = [a for a in data.alarms_of(sites) if a.kind == OUTAGE]
    if period.instant:
        down = {a.site_id for a in outages if a.open_at(period.end)}
        return round(100 * (len(sites) - len(down)) / len(sites), 2)
    length = (period.end - period.start).total_seconds()
    per_site = []
    for site in sites:
        spans = sorted(
            (max(a.opened, period.start), min(a.closed or period.end, period.end))
            for a in outages
            if a.site_id == site.id
        )
        down_s, cursor = 0.0, period.start
        for start, end in spans:
            start = max(start, cursor)
            if end > start:
                down_s += (end - start).total_seconds()
                cursor = end
        per_site.append(1 - down_s / length)
    return round(100 * sum(per_site) / len(per_site), 2)


def degraded(data: Dataset, sites: Sequence[Site], at: datetime) -> list[Site]:
    counts = Counter(a.site_id for a in open_at(data.alarms_of(sites), at))
    return [s for s in sites if counts[s.id] >= DEGRADED_OPEN_ALARMS]


def warn_open(answer: Answer, alarms: Sequence[Alarm]) -> None:
    stuck = sum(1 for a in alarms if a.kind in NEVER_CLOSED)
    answer.warn(
        "alarmas_abiertas_acumuladas",
        f"«alarmas abiertas» no es carga de trabajo: {stuck} de {len(alarms)} son de dos códigos "
        "de Alvic que nunca se cierran",
    )


def warn_printers(answer: Answer, alarms: Sequence[Alarm]) -> None:
    printers = sum(1 for a in alarms if a.kind == PRINTER)
    if alarms and printers / len(alarms) >= PRINTER_SHARE_WARNING:
        answer.warn(
            "ranking_dominado_por_impresoras",
            f"«{PRINTER}» supone {round(100 * printers / len(alarms))} % de las alarmas del "
            "ranking",
        )


def metric_facts(
    call: Call, metric: str, sites: Sequence[Site], period: Period, site: Site | None
) -> list[dict[str, Json]]:
    data, answer, estado = call.data, call.answer, call.text("estado")
    dims: dict[str, Json] = {} if estado is None else {"estado": estado}
    label = LABELS.get(metric, metric)

    def one(value: Json, unit: str) -> list[dict[str, Json]]:
        return [fact(metric, label, value, unit, metric=metric, site=site, dimensions=dims)]

    if metric in SNAPSHOT and not period.instant:
        answer.warn("metrica_instantanea", f"{metric} es una foto de ahora, no del periodo")
    ids = {s.id for s in sites}
    if metric == "monitores_ko":
        return one(sum(1 for m in data.monitors if m.site_id in ids and m.state == "ko"), "count")
    if metric == "estado_monitores":
        states = Counter(m.state for m in data.monitors if m.site_id in ids)
        return [
            fact(f"monitores_{state}", f"Monitores {state}", states[state], "count", site=site)
            for state in ("ok", "ko", "indeterminado")
        ] + [fact("monitores_total", "Monitores", sum(states.values()), "count", site=site)]
    alarms = data.alarms_of(sites)
    if metric == "alarmas":
        return one(len(raised(alarms, period, estado)), "count")
    if metric == "alarmas_abiertas":
        still_open = open_at(alarms, period.end)
        warn_open(answer, still_open)
        return one(len(still_open), "count")
    if metric == "disponibilidad":
        return one(availability(data, sites, period), "percent")
    if metric == "sedes_degradadas":
        found = degraded(data, sites, period.end)
        answer.warn(
            "sedes_degradadas_infladas",
            f"{len(found)} de {len(sites)} sedes superan {DEGRADED_OPEN_ALARMS} alarmas abiertas,"
            " infladas por los códigos que no se cierran",
        )
        return one(len(found), "count")
    carwashes = [s for s in sites if s.carwash]
    if metric == "lavaderos":
        return one(len(carwashes), "count")
    faulty = {a.site_id for a in open_at(alarms, period.end) if a.kind == CARWASH_FAULT}
    return one(sum(1 for s in carwashes if s.id not in faulty), "count")


def series(call: Call, alarms: Sequence[Alarm], period: Period, granularity: str) -> None:
    if period.instant:
        msg = "una serie necesita un periodo con duración, no «ahora»"
        raise ToolError(msg)
    step = STEPS[granularity]
    buckets: list[int] = []
    start = period.start
    while start < period.end:
        buckets.append(0)
        start += step
    for alarm in raised(alarms, period, call.text("estado")):
        buckets[int((alarm.opened - period.start) / step)] += 1
    rows: list[dict[str, Json]] = [
        {"desde": iso(period.start + n * step), "alarmas": count} for n, count in enumerate(buckets)
    ]
    call.answer.bounded_rows(rows)
    call.answer.facts = [
        fact(
            f"alarmas_{n + 1:03d}",
            f"Alarmas desde {row['desde']}",
            row["alarmas"],
            "count",
            metric="alarmas",
            dimensions={"desde": row["desde"], "granularidad": granularity},
        )
        for n, row in enumerate(call.answer.rows or [])
    ]


# --- Herramientas ----------------------------------------------------------------------------


def query_metric(call: Call) -> None:
    metric = str(call.args["metric"])
    period = call.period()
    site = call.site(call.args["site_id"]) if "site_id" in call.args else None
    sites: Sequence[Site] = (site,) if site is not None else call.scope()
    granularity = call.text("granularity")
    if granularity is not None:
        if metric != "alarmas":
            msg = f"la serie por {granularity} solo existe para «alarmas», no para {metric}"
            raise ToolError(msg)
        series(call, call.data.alarms_of(sites), period, granularity)
        return
    call.answer.facts = metric_facts(call, metric, sites, period, site)
    compare = call.text("compare_to")
    if compare is not None:
        if metric in SNAPSHOT:
            call.answer.warn("comparacion_no_aplica", f"{metric} es una foto: no se compara")
        else:
            shifted = period.shifted(compare)
            for item in metric_facts(call, metric, sites, shifted, site):
                dims = item["dimensions"]
                assert isinstance(dims, dict)
                call.answer.facts.append(
                    {
                        **item,
                        "key": f"{item['key']}_comparado",
                        "label": f"{item['label']} ({shifted.text})",
                        "dimensions": {**dims, "periodo": shifted.text},
                    }
                )
    if site is not None and metric in ("alarmas", "alarmas_abiertas"):
        alarms = call.data.alarms_of((site,))
        chosen = (
            open_at(alarms, period.end)
            if metric == "alarmas_abiertas"
            else raised(alarms, period, call.text("estado"))
        )
        call.answer.bounded_rows(
            [
                {
                    "id": a.id,
                    "tipo": a.kind,
                    "abierta": a.open_at(period.end),
                    "inicio": iso(a.opened),
                    "cierre": None if a.closed is None else iso(a.closed),
                    "descripcion": call.data.description(a),
                }
                for a in sorted(chosen, key=lambda a: (a.opened, a.id), reverse=True)
            ]
        )


def _group_key(group_by: str) -> Callable[[Site, Alarm | None], str]:
    def key(site: Site, alarm: Alarm | None) -> str:
        if group_by == "estacion":
            return site.id
        if group_by == "proveedor":
            return site.provider
        if group_by == "zona":
            return site.zone
        assert alarm is not None
        return alarm.kind

    return key


def top_n(call: Call) -> None:
    metric, group_by = str(call.args["metric"]), str(call.args["group_by"])
    limit = int(str(call.args.get("limit", 10)))
    period = call.period()
    sites = call.scope()
    by_id = {s.id: s for s in sites}
    key = _group_key(group_by)
    ranking: list[tuple[str, float]]
    if metric == "disponibilidad":
        if group_by == "tipo_alarma":
            msg = "la disponibilidad no se agrupa por tipo de alarma"
            raise ToolError(msg)
        groups: dict[str, list[Site]] = {}
        for site in sites:
            groups.setdefault(key(site, None), []).append(site)
        ranking = sorted(
            ((g, availability(call.data, members, period)) for g, members in groups.items()),
            key=lambda item: (item[1], item[0]),
        )
        unit = "percent"
    else:
        alarms = call.data.alarms_of(sites)
        chosen = (
            open_at(alarms, period.end)
            if metric == "alarmas_abiertas"
            else raised(alarms, period, call.text("estado"))
        )
        if metric == "alarmas_abiertas":
            warn_open(call.answer, chosen)
        warn_printers(call.answer, chosen)
        counts = Counter(key(by_id[a.site_id], a) for a in chosen)
        ranking = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        unit = "count"
    for rank, (group, amount) in enumerate(ranking[:limit], start=1):
        place = by_id.get(group) if group_by == "estacion" else None
        name = place.name if place is not None else group
        call.answer.facts.append(
            fact(
                f"top_{rank:02d}",
                f"{LABELS.get(metric, metric)} · {name}",
                amount if unit == "percent" else int(amount),
                unit,
                metric=metric,
                site=place,
                dimensions={group_by: name, "posicion": str(rank)},
            )
        )


def _dossier_sites(call: Call) -> tuple[tuple[Site, ...], dict[str, Json]]:
    kind = str(call.args["entity"])
    if kind == "site":
        if "id" not in call.args:
            msg = "build_dossier de una sede necesita id"
            raise InvalidParamsError(msg)
        site = call.site(call.args["id"])
        return (site,), entity(site)
    if kind == "zona":
        zone = normalize(str(call.args.get("id", "")))
        if call.principal.zone is not None and zone != call.principal.zone:
            msg = f"la zona {zone} no es la del operador"
            raise ToolError(msg)
        sites = tuple(s for s in call.data.sites if s.zone == zone)
        if not sites:
            msg = f"zona desconocida: {zone}"
            raise ToolError(msg)
        return sites, {"type": "zona", "id": zone, "name": zone}
    return call.scope(), {"type": "red", "id": "red", "name": "Red completa"}


def build_dossier(call: Call) -> None:
    period = call.period()
    sites, ref = _dossier_sites(call)
    visible = call.principal.visible_sites(call.data)
    alarms = raised(call.data.alarms_of(sites), period, None)
    network = raised(call.data.alarms_of(visible), period, None)
    facts: list[dict[str, Json]] = [
        {**fact("alarmas_total", "Alarmas del periodo", len(alarms), "count"), "entity": ref},
        fact(
            "alarmas_media_red",
            "Media de red por sede",
            round(len(network) / len(visible), 1),
            "count",
        ),
    ]
    if alarms:
        kind, amount = Counter(a.kind for a in alarms).most_common(1)[0]
        facts.append(
            fact(
                "tipo_dominante_pct",
                "Peso del tipo dominante",
                round(100 * amount / len(alarms), 1),
                "percent",
                dimensions={"tipo": kind},
            )
        )
    still_open = open_at(call.data.alarms_of(sites), period.end)
    warn_open(call.answer, still_open)
    ids = {s.id for s in sites}
    facts += [
        fact("alarmas_abiertas", "Alarmas abiertas al final del periodo", len(still_open), "count"),
        fact("disponibilidad", "Disponibilidad", availability(call.data, sites, period), "percent"),
        fact(
            "monitores_ko",
            "Monitores en KO ahora",
            sum(1 for m in call.data.monitors if m.site_id in ids and m.state == "ko"),
            "count",
        ),
    ]
    compare = call.text("compare_to")
    if compare is not None:
        shifted = period.shifted(compare)
        previous = raised(call.data.alarms_of(sites), shifted, None)
        facts.append(
            fact(
                "alarmas_total_comparado",
                f"Alarmas ({shifted.text})",
                len(previous),
                "count",
                dimensions={"periodo": shifted.text},
            )
        )
    call.answer.facts = facts


def correlate_events(call: Call) -> None:
    site = call.site(call.args["site_id"])
    window = str(call.args["window"])
    end = call.data.now
    start = end - WINDOWS[window]
    call.answer.period = Period(window, start, end, f"últimas {window} hasta {iso(end)}")
    alarms = sorted(
        (a for a in call.data.alarms_of((site,)) if start <= a.opened < end),
        key=lambda a: a.opened,
    )
    pairs: Counter[tuple[str, str]] = Counter()
    gap = timedelta(minutes=CORRELATION_MINUTES)
    for n, first in enumerate(alarms):
        for second in alarms[n + 1 :]:
            if second.opened - first.opened > gap:
                break
            if second.kind != first.kind:
                a, b = sorted((first.kind, second.kind))
                pairs[(a, b)] += 1
    total = sum(pairs.values())
    call.answer.facts = [
        fact(
            "pares_correlados",
            f"Pares de alarmas en menos de {CORRELATION_MINUTES} min",
            total,
            "count",
            site=site,
        )
    ]
    if total:
        (a, b), amount = pairs.most_common(1)[0]
        call.answer.facts.append(
            fact(
                "par_dominante_pct",
                "Peso del par más frecuente",
                round(100 * amount / total, 1),
                "percent",
                site=site,
                dimensions={"tipo_a": a, "tipo_b": b},
            )
        )


def get_situation_brief(call: Call) -> None:
    sites = call.scope()
    now = call.data.now
    alarms = call.data.alarms_of(sites)
    still_open = open_at(alarms, now)
    warn_open(call.answer, still_open)
    ids = {s.id for s in sites}
    call.answer.facts = [
        fact("alarmas_abiertas", "Alarmas abiertas ahora", len(still_open), "count"),
        fact(
            "alarmas_24h",
            "Alarmas de las últimas 24 horas",
            sum(1 for a in alarms if now - timedelta(hours=24) <= a.opened < now),
            "count",
        ),
        fact("sedes_degradadas", "Sedes degradadas", len(degraded(call.data, sites, now)), "count"),
        fact(
            "monitores_ko",
            "Monitores en KO",
            sum(1 for m in call.data.monitors if m.site_id in ids and m.state == "ko"),
            "count",
        ),
        fact("sedes_total", "Sedes", len(sites), "count"),
    ]


def _cost(a: str, b: str) -> float:
    """Distancia de edición con medio punto para las confusiones fonéticas."""
    previous = [float(i) for i in range(len(b) + 1)]
    for i, ca in enumerate(a, start=1):
        current = [float(i)]
        for j, cb in enumerate(b, start=1):
            swap = 0.0 if ca == cb else 0.5 if frozenset((ca, cb)) in _CLOSE_LETTERS else 1.0
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + swap))
        previous = current
    return previous[-1]


def site_resolver(call: Call) -> None:
    text = normalize(str(call.args["texto"]))
    candidates = sorted(
        (
            (min(_cost(text, s.key), _cost(text, normalize(s.code))), s.name, s)
            for s in call.data.sites
        ),
        key=lambda item: (item[0], item[1]),
    )
    cost, _, site = candidates[0]
    if cost > max(1.0, len(text) * _APPROX_SHARE):
        call.answer.warn("sin_coincidencia", f"ninguna sede se parece a «{call.args['texto']}»")
        return
    if cost > _EXACT_COST:
        call.answer.warn(
            "resolucion_aproximada",
            f"«{call.args['texto']}» se ha resuelto a {site.name}; confírmalo antes de seguir",
        )
    call.answer.facts = [
        fact("site_id", "Sede", site.id, None, site=site),
        fact("site_code", "Código de sede", site.code, None, site=site),
        fact("site_name", "Nombre de sede", site.name, None, site=site),
    ]


TOOLS: Final[dict[str, Callable[[Call], None]]] = {
    "site_resolver": site_resolver,
    "query_metric": query_metric,
    "top_n": top_n,
    "build_dossier": build_dossier,
    "correlate_events": correlate_events,
    "get_situation_brief": get_situation_brief,
}
