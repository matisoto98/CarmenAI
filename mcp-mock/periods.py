"""Interpretación de periodos de VigIA (5.16.1.1): ahora, hoy, 7, 30 o 90 días, mes actual, mes
anterior o un mes concreto, con tope de 400 días. Toda herramienta con periodo lo declara en
period_interpreted (6.4), con su texto en castellano.
"""

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final

from mock_errors import InvalidParamsError, ToolError

MAX_DAYS: Final = 400
MONTHS: Final = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)
_MONTH: Final = re.compile(r"^(20[0-9]{2})-(0[1-9]|1[0-2])$")
_DAYS: Final = {"7d": 7, "30d": 30, "90d": 90}


@dataclass(frozen=True, slots=True)
class Period:
    expression: str
    start: datetime
    end: datetime
    text: str

    @property
    def instant(self) -> bool:
        return self.start == self.end

    def interpreted(self) -> dict[str, str]:
        return {
            "expression": self.expression,
            "from": iso(self.start),
            "to": iso(self.end),
            "text": self.text,
        }

    def shifted(self, compare_to: str) -> "Period":
        if compare_to == "periodo_anterior":
            length = self.end - self.start
            if self.expression in ("mes_anterior", "mes_actual") or _MONTH.match(self.expression):
                start = _add_months(self.start, -1)
                end = start + length if self.expression == "mes_actual" else self.start
            else:
                start, end = self.start - length, self.start
            text = f"periodo anterior: {_span_text(start, end)}"
        else:
            start, end = _add_months(self.start, -12), _add_months(self.end, -12)
            text = f"mismo periodo del año anterior: {_span_text(start, end)}"
        return Period(f"{self.expression}~{compare_to}", start, end, text)


def iso(at: datetime) -> str:
    return at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_now(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def _add_months(at: datetime, months: int) -> datetime:
    index = at.year * 12 + at.month - 1 + months
    return at.replace(year=index // 12, month=index % 12 + 1)


def _month_start(at: datetime) -> datetime:
    return at.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _day(at: datetime) -> str:
    return f"{at.day} de {MONTHS[at.month - 1]} de {at.year}"


def _span_text(start: datetime, end: datetime) -> str:
    return f"del {_day(start)} al {_day(end)}"


def interpret(expression: str, now: datetime) -> Period:
    if expression == "ahora":
        return Period(expression, now, now, f"ahora ({now:%d/%m/%Y %H:%M} UTC)")
    if expression == "hoy":
        start = now.replace(hour=0, minute=0, second=0)
        return Period(expression, start, now, f"hoy, {_day(now)}, hasta las {now:%H:%M} UTC")
    if expression in _DAYS:
        days = _DAYS[expression]
        start = now - timedelta(days=days)
        return Period(expression, start, now, f"últimos {days} días ({_span_text(start, now)})")
    if expression == "mes_actual":
        start = _month_start(now)
        text = f"del {start.day} al {now.day} de {MONTHS[now.month - 1]} de {now.year}"
        return Period(expression, start, now, text)
    if expression == "mes_anterior":
        end = _month_start(now)
        start = _add_months(end, -1)
        return Period(expression, start, end, f"{MONTHS[start.month - 1]} de {start.year}")
    match = _MONTH.match(expression)
    if match is None:
        msg = f"periodo no admitido: {expression!r}"
        raise InvalidParamsError(msg)
    start = datetime(int(match[1]), int(match[2]), 1, tzinfo=UTC)
    if start > now:
        msg = f"el periodo {expression} es futuro"
        raise ToolError(msg)
    if (now - start).days > MAX_DAYS:
        msg = f"consulta rechazada: el periodo {expression} supera el tope de {MAX_DAYS} días"
        raise ToolError(msg)
    end = min(_add_months(start, 1), now)
    return Period(expression, start, end, f"{MONTHS[start.month - 1]} de {start.year}")
