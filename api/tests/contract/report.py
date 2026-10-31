"""Informe de conformidad MCP: lo que la batería observa, en Markdown (Prompt 10).

Con `--report RUTA` la batería de contrato no se limita a pasar o fallar: cada prueba anota lo
que ve en una sección y conftest.py recoge el resultado de cada una. Al terminar la sesión se
escribe el informe, aunque fallen pruebas: el modo informe registra cada fallo y no aborta.

El informe responde a las preguntas de Prompt 10 en este orden: transporte, batería, forma del
sobre frente a 6.4, hechos con procedencia, period_interpreted, identidad (7.8.1), herramientas
frente al golden set y reglas de interpretación de 5.16.1.1. Nunca lleva credenciales: por stdio
el token lo pone el puente y la batería no lo ve; por HTTP, el token se tacha antes de escribir.
"""

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Final

from contract.mcp_client import Json, ToolResult

SECTIONS: Final = (
    ("destino", "Destino y transporte"),
    ("bateria", "Batería de contrato (Prompt 9) en modo informe"),
    ("sobre", "Forma del sobre y diferencias con 6.4"),
    ("hechos", "Hechos identificables y procedencia"),
    ("periodo", "Periodo interpretado"),
    ("identidad", "Identidad delegada (7.8.1)"),
    ("catalogo", "Herramientas y golden set"),
    ("reglas", "Reglas de interpretación de 5.16.1.1"),
)
SECTION_IDS: Final = frozenset(key for key, _ in SECTIONS)
REDACTED: Final = "«credencial tachada»"
MAX_LINE: Final = 400


@dataclass(frozen=True, slots=True)
class Outcome:
    """Resultado de una prueba: passed, failed, skipped o error, con su motivo en una línea."""

    nodeid: str
    outcome: str
    message: str


@dataclass(frozen=True, slots=True)
class Sample:
    """Una llamada de ejemplo a una herramienta: el sobre que devolvió o el error."""

    tool: dict[str, Json]
    arguments: dict[str, Json]
    result: ToolResult | None
    error: str | None

    @property
    def name(self) -> str:
        return str(self.tool.get("name"))


@dataclass(slots=True)
class Findings:
    """Lo observado en una sesión de pytest, por sistema y por sección del informe."""

    generated_at: str
    profile: str
    notes: dict[str, list[str]] = field(default_factory=dict)
    outcomes: list[Outcome] = field(default_factory=list)
    catalogs: dict[str, list[dict[str, Json]]] = field(default_factory=dict)
    server_info: dict[str, dict[str, Json]] = field(default_factory=dict)
    samples: dict[str, list[Sample]] = field(default_factory=dict)

    def note(self, section: str, line: str) -> None:
        if section not in SECTION_IDS:
            msg = f"sección de informe desconocida: {section}"
            raise ValueError(msg)
        lines = self.notes.setdefault(section, [])
        if line not in lines:
            lines.append(line)


def first_lines(message: str) -> list[str]:
    """El mensaje de un fallo sin la reescritura de `assert` que añade pytest."""
    kept: list[str] = []
    for line in message.splitlines():
        if line.startswith(("assert ", "AssertionError")):
            break
        if line.strip():
            kept.append(line.strip())
    return kept or [message.strip().splitlines()[0] if message.strip() else "sin detalle"]


def _cell(text: str) -> str:
    return _clip(text).replace("|", "\\|")


def _clip(text: str) -> str:
    return text if len(text) <= MAX_LINE else text[: MAX_LINE - 1] + "…"


def _test_name(nodeid: str) -> str:
    return nodeid.rsplit("/", 1)[-1]


def _summary(outcomes: list[Outcome]) -> list[str]:
    counts = {kind: sum(o.outcome == kind for o in outcomes) for kind in ("passed", "failed")}
    skipped = sum(o.outcome == "skipped" for o in outcomes)
    errors = sum(o.outcome == "error" for o in outcomes)
    failing = counts["failed"] + errors
    verdict = (
        "Todas las comprobaciones pasan."
        if not failing
        else f"{failing} comprobaciones fallan: el servidor no cumple el contrato tal cual y "
        "agent.vigia no puede certificarse sin cambios en el servidor o un adaptador (7.11.3)."
    )
    return [
        "| Pruebas | Pasan | Fallan | Errores | Omitidas |",
        "|---|---|---|---|---|",
        f"| {len(outcomes)} | {counts['passed']} | {counts['failed']} | {errors} | {skipped} |",
        "",
        verdict,
    ]


def _battery(outcomes: list[Outcome]) -> list[str]:
    if not outcomes:
        return ["- No se ejecutó ninguna prueba."]
    lines = ["| Prueba | Resultado | Motivo |", "|---|---|---|"]
    details: list[str] = []
    for outcome in outcomes:
        detail = first_lines(outcome.message) if outcome.message else []
        lines.append(
            f"| `{_cell(_test_name(outcome.nodeid))}` | {outcome.outcome} | "
            f"{_cell(detail[0]) if detail else ''} |"
        )
        if outcome.outcome in ("failed", "error") and len(detail) > 1:
            details.append(f"- `{_test_name(outcome.nodeid)}`:")
            details.extend(f"  - {_clip(line)}" for line in detail)
    if details:
        lines.extend(["", "Detalle de cada fallo:", "", *details])
    return lines


def render(findings: Findings, *, secrets: Iterable[str] = ()) -> str:
    systems = sorted(findings.catalogs) or sorted(findings.server_info) or ["sin destino"]
    out = [
        f"# Conformidad MCP: {', '.join(systems)}",
        "",
        f"Informe generado por la batería de contrato en modo informe (Prompt 10) el "
        f"{findings.generated_at}, perfil `{findings.profile}`. Registra cada fallo y no aborta. "
        "No contiene credenciales.",
        "",
        "## Resumen",
        "",
        *_summary(findings.outcomes),
    ]
    for number, (key, title) in enumerate(SECTIONS, start=1):
        out.extend(["", f"## {number}. {title}", ""])
        if key == "bateria":
            out.extend(_battery(findings.outcomes))
            continue
        notes = findings.notes.get(key, [])
        out.extend(notes or ["- Sin observaciones: ninguna prueba de esta sección se ejecutó."])
    for system in systems:
        if system not in findings.catalogs:
            continue
        catalog = {
            "server_info": findings.server_info.get(system, {}),
            "tools": findings.catalogs[system],
        }
        out.extend(
            [
                "",
                f"## Anexo: catálogo observado de {system}",
                "",
                "```json",
                json.dumps(catalog, ensure_ascii=False, indent=2, sort_keys=True),
                "```",
            ]
        )
    text = "\n".join(out) + "\n"
    for secret in secrets:
        if secret:
            text = text.replace(secret, REDACTED)
    return text
