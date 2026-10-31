"""El sobre canónico de 6.4: facts, passages y media siempre presentes, aunque vayan vacíos."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Final

from periods import Period, iso

type Json = None | bool | int | float | str | list[Json] | dict[str, Json]

SCHEMA_VERSION: Final = "1.0"
MAX_ROWS: Final = 500


@dataclass(slots=True)
class Answer:
    """Lo que calcula una herramienta; el servidor le pone la cabecera del sobre."""

    facts: list[dict[str, Json]] = field(default_factory=list)
    passages: list[dict[str, Json]] = field(default_factory=list)
    media: list[dict[str, Json]] = field(default_factory=list)
    rows: list[dict[str, Json]] | None = None
    warnings: list[dict[str, Json]] = field(default_factory=list)
    period: Period | None = None
    partial: bool = False

    def warn(self, code: str, message: str) -> None:
        if all(w["code"] != code for w in self.warnings):
            self.warnings.append({"code": code, "message": message})

    def bounded_rows(self, rows: list[dict[str, Json]]) -> None:
        """rows está acotado por contrato: lo que pasa del tope se recorta y se declara."""
        if len(rows) > MAX_ROWS:
            self.partial = True
            self.warn(
                "recortado",
                f"respuesta recortada a {MAX_ROWS} filas de {len(rows)}; acota el periodo",
            )
        self.rows = rows[:MAX_ROWS]


@dataclass(frozen=True, slots=True)
class Header:
    system_id: str
    tool_name: str
    call_id: str
    correlation_id: str
    generated_at: datetime
    catalog_version: str


def build(header: Header, answer: Answer) -> dict[str, Json]:
    envelope: dict[str, Json] = {
        "schema_version": SCHEMA_VERSION,
        "system_id": header.system_id,
        "tool_name": header.tool_name,
        "call_id": header.call_id,
        "correlation_id": header.correlation_id,
        "generated_at": iso(header.generated_at),
        "catalog_version": header.catalog_version,
    }
    if answer.period is not None:
        interpreted: dict[str, Json] = dict(answer.period.interpreted())
        envelope["period_interpreted"] = interpreted
    envelope["facts"] = list(answer.facts)
    if answer.rows is not None:
        envelope["rows"] = list(answer.rows)
    envelope["passages"] = list(answer.passages)
    envelope["media"] = list(answer.media)
    envelope["warnings"] = list(answer.warnings)
    envelope["partial"] = answer.partial
    envelope["next_cursor"] = None
    return envelope


def break_contract(envelope: dict[str, Json]) -> dict[str, Json]:
    """Modo invalid: sin passages y con partial=true sin avisos."""
    broken = {k: v for k, v in envelope.items() if k != "passages"}
    broken["partial"] = True
    broken["warnings"] = []
    return broken
