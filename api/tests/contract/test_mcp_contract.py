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

import pytest

from contract.conftest import Target
from contract.envelope_checks import (
    CORRELATION,
    RESULT_KINDS,
    ROLES,
    TOOL_NAME,
    envelope_problems,
    example_arguments,
)
from contract.mcp_client import (
    PROTOCOL_VERSION,
    Json,
    McpClient,
    McpError,
    McpHttpError,
    McpRpcError,
    as_list,
    as_object,
)

pytestmark = pytest.mark.contract

METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
UNAUTHORIZED = 401

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
        try:
            result = client.call_tool(
                str(tool["name"]), example_arguments(tool), correlation_id=CORRELATION
            )
        except McpError as error:  # en modo informe se anota y se sigue con la siguiente
            problems.append(f"{tool.get('name')}: {error}")
            continue
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
    if target.command is not None:
        pytest.skip("por stdio la credencial la pone el puente; lo mide test_conformance.py")
    client = McpClient(target.url, token=None)
    with pytest.raises(McpHttpError) as raised:
        client.initialize()
    assert raised.value.status == UNAUTHORIZED
