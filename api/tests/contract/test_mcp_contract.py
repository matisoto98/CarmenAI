"""Prompt 9: batería de contrato MCP (6.4, 6.9.4), la misma para el simulado y los reales.

Independiente de Carmen: no importa `carmen`, habla MCP con su propio cliente mínimo y valida cada
sobre contra contracts/mcp-envelope.schema.json. El destino se elige en conftest.py: por defecto,
los dos sistemas de mcp-mock; con CARMEN_MCP_TARGETS, cualquier servidor.

Lo que no cabe en el esquema se comprueba aquí:
  - el sobre nombra el sistema, la herramienta y la correlación de la llamada;
  - lo que devuelve corresponde a su result_kind declarado;
  - toda herramienta con periodo devuelve period_interpreted;
  - los errores (herramienta desconocida, argumentos inválidos, método desconocido, sin token)
    son errores, nunca un sobre vacío con apariencia de respuesta.
"""

import json
import re
from collections.abc import Iterator
from functools import cache
from pathlib import Path
from typing import Final

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012, Schema

from contract.conftest import Target
from contract.mcp_client import (
    PROTOCOL_VERSION,
    Json,
    McpClient,
    McpHttpError,
    McpRpcError,
    ToolResult,
    as_list,
    as_object,
)

pytestmark = pytest.mark.contract

CONTRACTS: Final = Path(__file__).resolve().parents[3] / "contracts"
ROLES: Final = {"ADMIN", "MANAGER", "OPERATOR", "AUDITOR"}
RESULT_KINDS: Final = {"facts", "passages", "media", "mixed"}
TOOL_NAME: Final = re.compile(r"^[a-z][a-z0-9_]{1,47}$")
CORRELATION: Final = "cor_contrato01"
METHOD_NOT_FOUND: Final = -32601
INVALID_PARAMS: Final = -32602
UNAUTHORIZED: Final = 401

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


# --- La batería ------------------------------------------------------------------------------


def test_initialize_negotiates_the_protocol_and_offers_tools(target: Target) -> None:
    client = target.client()
    info = client.initialize()
    assert info.get("protocolVersion") == PROTOCOL_VERSION
    assert "tools" in as_object(info.get("capabilities", {}))
    assert as_object(info.get("serverInfo", {})).get("name")
    client.close()


def test_every_tool_is_described_with_its_result_kind_and_roles(target: Target) -> None:
    client = target.client()
    client.initialize()
    tools = client.list_tools()
    client.close()
    assert tools, "el servidor no ofrece herramientas"
    problems = []
    for tool in tools:
        name = str(tool.get("name"))
        if not TOOL_NAME.match(name):
            problems.append(f"{name}: nombre fuera del patrón del sobre")
        if not str(tool.get("description", "")).strip():
            problems.append(f"{name}: sin descripción")
        if as_object(tool.get("inputSchema", {})).get("type") != "object":
            problems.append(f"{name}: inputSchema no es un objeto")
        if tool.get("result_kind") not in RESULT_KINDS:
            problems.append(f"{name}: result_kind={tool.get('result_kind')!r} (6.9.4)")
        roles = tool.get("roles")
        if not isinstance(roles, list) or not roles or not set(map(str, roles)) <= ROLES:
            problems.append(f"{name}: roles={roles!r} (6.9.4)")
    assert not problems, "\n".join(problems)


def test_every_tool_answers_with_a_valid_envelope(target: Target) -> None:
    client = target.client()
    client.initialize()
    problems: list[str] = []
    for tool in client.list_tools():
        result = client.call_tool(
            str(tool["name"]), example_arguments(tool), correlation_id=CORRELATION
        )
        problems.extend(envelope_problems(target, tool, result))
    client.close()
    assert not problems, "\n".join(problems)


def refuses(client: McpClient, name: str, arguments: dict[str, Json]) -> bool:
    """Rechazo como error JSON-RPC de parámetros o como resultado con isError."""
    try:
        result = client.call_tool(name, arguments)
    except McpRpcError as error:
        return error.code == INVALID_PARAMS
    return result.is_error


def test_an_unknown_tool_is_an_error(target: Target) -> None:
    client = target.client()
    client.initialize()
    refused = refuses(client, "herramienta_que_no_existe", {})
    client.close()
    assert refused, "una herramienta desconocida devolvió un resultado"


def test_invalid_arguments_are_rejected(target: Target) -> None:
    client = target.client()
    client.initialize()
    tools = client.list_tools()
    with_required = [
        t for t in tools if as_list(as_object(t.get("inputSchema", {})).get("required", []))
    ]
    assert with_required, "ninguna herramienta declara parámetros obligatorios"
    refused = refuses(client, str(with_required[0]["name"]), {})
    client.close()
    assert refused, "una llamada sin sus obligatorios devolvió un sobre"


def test_an_unknown_method_is_method_not_found(target: Target) -> None:
    client = target.client()
    client.initialize()
    with pytest.raises(McpRpcError) as raised:
        client.request("carmen/no_existe", {})
    client.close()
    assert raised.value.code == METHOD_NOT_FOUND


def test_a_request_without_a_token_is_refused(target: Target) -> None:
    client = McpClient(target.url, token=None)
    with pytest.raises(McpHttpError) as raised:
        client.initialize()
    assert raised.value.status == UNAUTHORIZED
