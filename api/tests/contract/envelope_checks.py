"""Comprobaciones del sobre MCP compartidas por la batería (Prompt 9) y el diagnóstico (Prompt 10).

Independientes de Carmen: validan contra contracts/ y generan argumentos de ejemplo a partir del
inputSchema que publica cada servidor.
"""

import json
import re
from collections.abc import Iterator
from functools import cache
from pathlib import Path
from typing import Final

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012, Schema

from contract.conftest import Target
from contract.mcp_client import Json, ToolResult, as_list, as_object

CONTRACTS: Final = Path(__file__).resolve().parents[3] / "contracts"
ROLES: Final = {"ADMIN", "MANAGER", "OPERATOR", "AUDITOR"}
RESULT_KINDS: Final = {"facts", "passages", "media", "mixed"}
TOOL_NAME: Final = re.compile(r"^[a-z][a-z0-9_]{1,47}$")
CORRELATION: Final = "cor_contrato01"

#: Valores plausibles para parámetros de texto, por nombre. Fuera de esta tabla se genera un
#: valor que cumple el esquema; el contrato exige un sobre válido en los dos casos.
HINTS: Final[dict[str, Json]] = {
    "texto": "Getafe",
    "site_id": "1",
    "id": "1",
    "query": "sonda de nivel sin datos",
    "term": "lavaderos",
    "document_id": "RB-041",
    "section": "2",
    "problema": "sonda de nivel sin datos",
    "equipo": "sonda",
    "media_id": "RB-041-fig2",
}
PATTERN_CANDIDATES: Final = ("RB-041", "2026-07", "1", "Getafe")


@cache
def envelope_validator() -> Draft202012Validator:
    resources = []
    for path in CONTRACTS.glob("*.schema.json"):
        schema = json.loads(path.read_text(encoding="utf-8"))
        resource = Resource.from_contents(schema, default_specification=DRAFT202012)
        resources.append((path.name, resource))
        resources.append((schema["$id"], resource))
    registry = Registry[Schema]().with_resources(resources)
    schema = json.loads((CONTRACTS / "mcp-envelope.schema.json").read_text(encoding="utf-8"))
    return Draft202012Validator(schema, registry=registry)


def schema_errors(envelope: Json) -> list[str]:
    return [
        f"{'/'.join(str(p) for p in e.absolute_path) or '<raíz>'}: {e.message}"
        for e in envelope_validator().iter_errors(envelope)
    ]


# --- Argumentos de ejemplo a partir del inputSchema ------------------------------------------


def example_value(name: str, schema: dict[str, Json]) -> Json:
    if name in HINTS and _accepts(schema, HINTS[name]):
        return HINTS[name]
    if "enum" in schema:
        return as_list(schema["enum"])[0]
    if "anyOf" in schema:
        return example_value(name, as_object(as_list(schema["anyOf"])[0]))
    kind = schema.get("type", "string")
    kinds = [k for k in as_list(kind) if k != "object"] if isinstance(kind, list) else [kind]
    first = kinds[0] if kinds else "string"
    if first == "integer":
        minimum = schema.get("minimum", 1)
        return minimum if isinstance(minimum, int) else 1
    if first == "number":
        return 1
    if first == "boolean":
        return True
    pattern = schema.get("pattern")
    if isinstance(pattern, str):
        return next((c for c in PATTERN_CANDIDATES if re.search(pattern, c)), "x")
    minimum = schema.get("minLength", 1)
    return "Getafe".ljust(minimum if isinstance(minimum, int) else 1, "x")


def _accepts(schema: dict[str, Json], value: Json) -> bool:
    return not list(Draft202012Validator(schema).iter_errors(value))


def example_arguments(tool: dict[str, Json]) -> dict[str, Json]:
    """Los obligatorios y los opcionales con valor conocido en HINTS."""
    schema = as_object(tool.get("inputSchema", {}))
    properties = as_object(schema.get("properties", {}))
    required = {str(r) for r in as_list(schema.get("required", []))}
    return {
        name: example_value(name, as_object(prop))
        for name, prop in properties.items()
        if name in required or name in HINTS
    }


def has_period(tool: dict[str, Json]) -> bool:
    schema = as_object(tool.get("inputSchema", {}))
    return "period" in as_object(schema.get("properties", {}))


# --- Comprobaciones de un sobre ---------------------------------------------------------------


def envelope_problems(target: Target, tool: dict[str, Json], result: ToolResult) -> Iterator[str]:
    name = str(tool["name"])
    if result.is_error:
        yield f"{name}: devolvió un error de herramienta: {result.text[:200]}"
        return
    if result.envelope is None:
        yield f"{name}: el resultado no lleva el sobre canónico (structuredContent ni JSON)"
        return
    envelope = result.envelope
    yield from (f"{name}: {e}" for e in schema_errors(envelope))
    if envelope.get("system_id") != target.system_id:
        yield f"{name}: system_id={envelope.get('system_id')!r}, se esperaba {target.system_id}"
    if envelope.get("tool_name") != name:
        yield f"{name}: tool_name={envelope.get('tool_name')!r}"
    if envelope.get("correlation_id") != CORRELATION:
        yield f"{name}: no devuelve la correlación de la llamada ({envelope.get('correlation_id')})"
    if has_period(tool) and "period_interpreted" not in envelope:
        yield f"{name}: tiene periodo y no devuelve period_interpreted (6.4)"
    kind = tool.get("result_kind")
    empty = {key: not envelope.get(key) for key in ("facts", "passages", "media")}
    if kind == "facts" and not (empty["passages"] and empty["media"]):
        yield f"{name}: declara facts y devuelve passages o media"
    if kind in ("passages", "media") and not empty["facts"]:
        yield f"{name}: declara {kind} y devuelve facts"
