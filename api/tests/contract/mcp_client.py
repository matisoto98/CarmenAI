"""Cliente MCP mínimo de las pruebas de contrato (Prompts 9 y 10).

Habla MCP con la biblioteca estándar por dos transportes:
  - HTTP transmitible (streamable HTTP): JSON-RPC 2.0 por POST, identificador de sesión en
    `Mcp-Session-Id` y respuestas en JSON o en un flujo SSE;
  - stdio: lanza un proceso (el puente vigia-mcp-bridge.mjs de 4.6.6) y le habla JSON-RPC, un
    mensaje por línea. El puente presenta el certificado de cliente y pone el token de Entra; el
    cliente nunca lo ve.
No usa el adaptador de Carmen (Prompt 11) ni importa nada de `carmen`: la batería tiene que poder
apuntarse a cualquier servidor, incluido el MCP real de VigIA (Prompt 10).
"""

import itertools
import json
import queue
import ssl
import subprocess
import threading
import urllib.error
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass, field
from http import HTTPStatus
from http.client import HTTPResponse, RemoteDisconnected
from typing import IO, Final

type Json = None | bool | int | float | str | list[Json] | dict[str, Json]

PROTOCOL_VERSION: Final = "2025-11-25"
_ACCEPT: Final = "application/json, text/event-stream"


class McpError(Exception):
    """Cualquier fallo de una petición MCP: HTTP, JSON-RPC o transporte."""


class McpHttpError(McpError):
    """El servidor respondió con un estado HTTP de error (401, 403, 5xx…)."""

    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"HTTP {status}: {body[:200]}")
        self.status = status
        self.body = body


class McpRpcError(McpError):
    """Error JSON-RPC: método desconocido, parámetros inválidos, herramienta inexistente…"""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(f"JSON-RPC {code}: {message}")
        self.code = code
        self.message = message


class McpTransportError(McpError):
    """La conexión se cayó o el servidor no respondió en el plazo."""


@dataclass(frozen=True, slots=True)
class ToolResult:
    """Resultado de tools/call: el sobre canónico (6.4) o un error de herramienta."""

    is_error: bool
    envelope: dict[str, Json] | None
    text: str
    structured: bool = False


class StdioConnection:
    """Un proceso que habla MCP por stdio: una línea JSON por mensaje, en los dos sentidos.

    La salida de error del proceso se descarta por defecto: el puente puede escribir allí detalles
    de su sesión y nada de eso debe acabar en la salida de pytest ni en el informe.
    """

    def __init__(self, command: Sequence[str], *, show_stderr: bool = False) -> None:
        try:
            self._process = subprocess.Popen(
                list(command),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=None if show_stderr else subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                bufsize=1,
            )
        except OSError as error:
            msg = f"no se pudo lanzar {command[0]!r}: {error.strerror or error}"
            raise McpTransportError(msg) from error
        self._lines: queue.Queue[str | None] = queue.Queue()
        stdout = self._process.stdout
        assert stdout is not None
        self._reader = threading.Thread(target=self._read, args=(stdout,), daemon=True)
        self._reader.start()

    def _read(self, stdout: IO[str]) -> None:
        for line in stdout:
            self._lines.put(line)
        self._lines.put(None)

    def send(self, message: dict[str, Json]) -> None:
        stdin = self._process.stdin
        assert stdin is not None
        try:
            stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
            stdin.flush()
        except (BrokenPipeError, ValueError) as error:
            msg = f"el proceso stdio terminó (código {self._process.poll()})"
            raise McpTransportError(msg) from error

    def receive(self, message_id: int, timeout_s: float) -> dict[str, Json]:
        """La respuesta con ese id; descarta notificaciones y otras líneas del servidor."""
        while True:
            try:
                line = self._lines.get(timeout=timeout_s)
            except queue.Empty:
                msg = f"sin respuesta del proceso stdio en {timeout_s:g} s"
                raise McpTransportError(msg) from None
            if line is None:
                msg = f"el proceso stdio terminó (código {self._process.wait(timeout=5)})"
                raise McpTransportError(msg)
            try:
                decoded: Json = json.loads(line)
            except json.JSONDecodeError:
                continue  # una línea que no es JSON-RPC (traza del puente) no es una respuesta
            if isinstance(decoded, dict) and decoded.get("id") == message_id:
                return decoded

    def close(self) -> None:
        if self._process.stdin is not None:
            self._process.stdin.close()
        try:
            self._process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._process.terminate()
            self._process.wait(timeout=5)
        if self._process.stdout is not None:
            self._process.stdout.close()
        self._reader.join(timeout=5)


@dataclass(slots=True)
class McpClient:
    """Cliente MCP. Con `command` habla stdio con ese proceso y `url` es solo una etiqueta."""

    url: str
    token: str | None
    timeout_s: float = 10.0
    session_id: str | None = None
    server_info: dict[str, Json] = field(default_factory=dict)
    command: tuple[str, ...] | None = None
    ssl_context: ssl.SSLContext | None = None
    show_stderr: bool = False
    _stdio: StdioConnection | None = None
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
        return ToolResult(
            is_error=result.get("isError") is True,
            envelope=envelope,
            text=text,
            structured=isinstance(structured, dict),
        )

    def close(self) -> None:
        if self._stdio is not None:
            self._stdio.close()
            self._stdio = None
            return
        if self.session_id is None:
            return
        request = urllib.request.Request(self.url, method="DELETE", headers=self._headers())
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s, context=self.ssl_context):
                pass
        except (urllib.error.URLError, OSError):
            pass
        self.session_id = None

    # --- JSON-RPC ----------------------------------------------------------------------

    def request(self, method: str, params: dict[str, Json]) -> Json:
        message_id = next(self._ids)
        body: dict[str, Json] = {
            "jsonrpc": "2.0",
            "id": message_id,
            "method": method,
            "params": params,
        }
        if self.command is not None:
            stdio = self._connection()
            stdio.send(body)
            reply = stdio.receive(message_id, self.timeout_s)
        else:
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
        if self.command is not None:
            self._connection().send(body)
        else:
            self._post(body)

    def _connection(self) -> StdioConnection:
        if self._stdio is None:
            assert self.command is not None
            self._stdio = StdioConnection(self.command, show_stderr=self.show_stderr)
        return self._stdio

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
            with urllib.request.urlopen(
                request, timeout=self.timeout_s, context=self.ssl_context
            ) as raw:
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
