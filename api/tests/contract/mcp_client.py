"""Cliente MCP mínimo de las pruebas de contrato (Prompt 9).

Habla MCP sobre HTTP transmitible (streamable HTTP) con la biblioteca estándar: JSON-RPC 2.0 por
POST, identificador de sesión en `Mcp-Session-Id` y respuestas en JSON o en un flujo SSE. No usa
el adaptador de Carmen (Prompt 11) ni importa nada de `carmen`: la batería tiene que poder
apuntarse a cualquier servidor, incluido el MCP real de VigIA (Prompt 10).
"""

import itertools
import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from http import HTTPStatus
from http.client import HTTPResponse, RemoteDisconnected
from typing import Final

type Json = None | bool | int | float | str | list[Json] | dict[str, Json]

PROTOCOL_VERSION: Final = "2025-11-25"
_ACCEPT: Final = "application/json, text/event-stream"


class McpHttpError(Exception):
    """El servidor respondió con un estado HTTP de error (401, 403, 5xx…)."""

    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"HTTP {status}: {body[:200]}")
        self.status = status
        self.body = body


class McpRpcError(Exception):
    """Error JSON-RPC: método desconocido, parámetros inválidos, herramienta inexistente…"""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(f"JSON-RPC {code}: {message}")
        self.code = code
        self.message = message


class McpTransportError(Exception):
    """La conexión se cayó o el servidor no respondió en el plazo."""


@dataclass(frozen=True, slots=True)
class ToolResult:
    """Resultado de tools/call: el sobre canónico (6.4) o un error de herramienta."""

    is_error: bool
    envelope: dict[str, Json] | None
    text: str


@dataclass(slots=True)
class McpClient:
    url: str
    token: str | None
    timeout_s: float = 10.0
    session_id: str | None = None
    server_info: dict[str, Json] = field(default_factory=dict)
    _ids: "itertools.count[int]" = field(default_factory=lambda: itertools.count(1))

    # --- protocolo ---------------------------------------------------------------------

    def initialize(self) -> dict[str, Json]:
        result = self.request(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "carmen-contract-tests", "version": "1.0"},
            },
        )
        info = as_object(result)
        self.server_info = info
        self.notify("notifications/initialized")
        return info

    def list_tools(self) -> list[dict[str, Json]]:
        tools: list[dict[str, Json]] = []
        cursor: str | None = None
        while True:
            params: dict[str, Json] = {} if cursor is None else {"cursor": cursor}
            page = as_object(self.request("tools/list", params))
            tools.extend(as_object(t) for t in as_list(page.get("tools")))
            next_cursor = page.get("nextCursor")
            if not isinstance(next_cursor, str) or not next_cursor:
                return tools
            cursor = next_cursor

    def call_tool(
        self, name: str, arguments: dict[str, Json], *, correlation_id: str | None = None
    ) -> ToolResult:
        params: dict[str, Json] = {"name": name, "arguments": arguments}
        if correlation_id is not None:
            params["_meta"] = {"correlation_id": correlation_id}
        result = as_object(self.request("tools/call", params))
        texts = [
            str(item.get("text", ""))
            for item in (as_object(c) for c in as_list(result.get("content", [])))
            if item.get("type") == "text"
        ]
        text = "\n".join(texts)
        structured = result.get("structuredContent")
        envelope: dict[str, Json] | None = None
        if isinstance(structured, dict):
            envelope = structured
        elif texts:
            try:
                parsed = json.loads(texts[0])
            except json.JSONDecodeError:
                parsed = None
            envelope = parsed if isinstance(parsed, dict) else None
        return ToolResult(is_error=result.get("isError") is True, envelope=envelope, text=text)

    def close(self) -> None:
        if self.session_id is None:
            return
        request = urllib.request.Request(self.url, method="DELETE", headers=self._headers())
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s):
                pass
        except (urllib.error.URLError, OSError):
            pass
        self.session_id = None

    # --- JSON-RPC sobre HTTP -----------------------------------------------------------

    def request(self, method: str, params: dict[str, Json]) -> Json:
        message_id = next(self._ids)
        body: dict[str, Json] = {
            "jsonrpc": "2.0",
            "id": message_id,
            "method": method,
            "params": params,
        }
        response = self._post(body)
        if response is None:
            msg = f"{method}: el servidor no devolvió respuesta"
            raise McpTransportError(msg)
        reply = _pick_reply(response, message_id)
        error = reply.get("error")
        if isinstance(error, dict):
            code = error.get("code")
            raise McpRpcError(code if isinstance(code, int) else 0, str(error.get("message")))
        return reply.get("result")

    def notify(self, method: str, params: dict[str, Json] | None = None) -> None:
        body: dict[str, Json] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            body["params"] = params
        self._post(body)

    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": _ACCEPT,
            "MCP-Protocol-Version": PROTOCOL_VERSION,
        }
        if self.token is not None:
            headers["Authorization"] = f"Bearer {self.token}"
        if self.session_id is not None:
            headers["Mcp-Session-Id"] = self.session_id
        return headers

    def _post(self, body: dict[str, Json]) -> str | None:
        data = json.dumps(body, ensure_ascii=False).encode()
        request = urllib.request.Request(
            self.url, data=data, method="POST", headers=self._headers()
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as raw:
                response: HTTPResponse = raw
                session = response.headers.get("Mcp-Session-Id")
                if session:
                    self.session_id = session
                if response.status == HTTPStatus.ACCEPTED:  # notificación aceptada
                    return None
                content_type = response.headers.get("Content-Type", "")
                text = response.read().decode()
        except urllib.error.HTTPError as error:
            with error:
                detail = error.read().decode(errors="replace")
            raise McpHttpError(error.code, detail) from error
        except (RemoteDisconnected, ConnectionError, TimeoutError) as error:
            raise McpTransportError(str(error) or type(error).__name__) from error
        except urllib.error.URLError as error:
            raise McpTransportError(str(error.reason)) from error
        if "text/event-stream" in content_type:
            return _sse_payloads(text)
        return text


def _sse_payloads(stream: str) -> str:
    """Junta los mensajes JSON-RPC de un flujo SSE en una lista JSON."""
    messages: list[str] = []
    data: list[str] = []
    for line in [*stream.splitlines(), ""]:
        if line.startswith("data:"):
            data.append(line[5:].lstrip())
        elif not line and data:
            messages.append("\n".join(data))
            data = []
    return "[" + ",".join(messages) + "]"


def _pick_reply(text: str, message_id: int) -> dict[str, Json]:
    decoded: Json = json.loads(text)
    candidates = decoded if isinstance(decoded, list) else [decoded]
    for candidate in candidates:
        if isinstance(candidate, dict) and candidate.get("id") == message_id:
            return candidate
    msg = f"ninguna respuesta JSON-RPC lleva el id {message_id}"
    raise McpTransportError(msg)


def as_object(value: Json) -> dict[str, Json]:
    if not isinstance(value, dict):
        msg = f"se esperaba un objeto JSON y llegó {type(value).__name__}"
        raise TypeError(msg)
    return value


def as_list(value: Json) -> list[Json]:
    if not isinstance(value, list):
        msg = f"se esperaba una lista JSON y llegó {type(value).__name__}"
        raise TypeError(msg)
    return value
