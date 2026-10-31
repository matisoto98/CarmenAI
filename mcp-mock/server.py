"""Servidor MCP simulado de Carmen (Prompt 9): determinista y conforme al contrato de 6.4.

Habla MCP (protocolo 2025-11-25) sobre HTTP transmitible con solo la biblioteca estándar:
JSON-RPC 2.0 por POST en /<sistema>/mcp, sesión en `Mcp-Session-Id` y respuestas JSON. Sirve
dos sistemas con los catálogos del golden set: `vigia` (métricas) y `plenmind` (documental).

    python mcp-mock/server.py --port 8765

Configuración por entorno:
    MCP_MOCK_SEED        semilla del conjunto de datos (20260727)
    MCP_MOCK_NOW         instante de referencia, UTC (2026-07-27T09:14:22Z)
    MCP_MOCK_FAILURES    modos de fallo (ver failure_modes.py)
    MCP_MOCK_PUBLIC_URL  base de los enlaces a documentos y media (por defecto, la del Host)

Al quedar listo escribe `MCP_MOCK_READY <puerto>` en la salida estándar.
"""

import argparse
import hashlib
import itertools
import json
import os
import re
import secrets
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Final

sys.path.insert(0, str(Path(__file__).resolve().parent))

import catalog
import dataset
import documents
import envelope
import identity
import plenmind_tools
import vigia_tools
from envelope import Json
from failure_modes import FailureConfigError, FailurePlan, Mode
from mock_errors import ForbiddenError, InvalidParamsError, MockError, ToolError, UnauthorizedError
from periods import parse_now

PROTOCOL_VERSION: Final = "2025-11-25"
SERVER_NAME: Final = "carmen-mcp-mock"
SERVER_VERSION: Final = "1.0.0"
DEFAULT_SEED: Final = 20260727
DEFAULT_NOW: Final = "2026-07-27T09:14:22Z"
SYSTEMS: Final = ("vigia", "plenmind")
METHOD_NOT_FOUND: Final = -32601
PARSE_ERROR: Final = -32700
INVALID_REQUEST: Final = -32600
_CORRELATION: Final = re.compile(r"^cor_[A-Za-z0-9]{1,60}$")
_ENDPOINT: Final = re.compile(r"^/([a-z]+)/mcp/?$")
_MEDIA: Final = re.compile(r"^/media/([A-Z]{2,4}-[0-9]{3,5})/([a-z0-9]+)$")
_DOC: Final = re.compile(r"^/doc/([A-Z]{2,4}-[0-9]{3,5})$")


@dataclass(slots=True)
class MockState:
    seed: int
    now: datetime
    failures: FailurePlan
    public_url: str | None
    data: dataset.Dataset
    catalogs: dict[str, catalog.Catalog]
    sessions: set[str] = field(default_factory=set)
    lock: threading.Lock = field(default_factory=threading.Lock)
    counter: "itertools.count[int]" = field(default_factory=lambda: itertools.count(1))

    def call_id(self, session: str) -> str:
        with self.lock:
            n = next(self.counter)
        digest = hashlib.sha256(f"{self.seed}:{session}:{n}".encode()).hexdigest()
        return f"cal_{digest[:16]}"


class _DropConnectionError(Exception):
    """Modo down: cerrar la conexión sin responder."""


class MockHttpServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], state: MockState) -> None:
        super().__init__(address, Handler)
        self.state = state


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server: MockHttpServer

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002 - firma de la base
        """Silencioso: las pruebas leen la salida estándar."""

    # --- respuesta -----------------------------------------------------------------------

    def _send(
        self,
        status: int,
        body: bytes,
        content_type: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: Json, headers: dict[str, str] | None = None) -> None:
        self._send(
            status, json.dumps(payload, ensure_ascii=False).encode(), "application/json", headers
        )

    def _rpc_error(self, status: int, message_id: Json, code: int, message: str) -> None:
        headers = {"WWW-Authenticate": 'Bearer realm="carmen-mcp-mock"'} if status == 401 else None
        self._json(
            status,
            {"jsonrpc": "2.0", "id": message_id, "error": {"code": code, "message": message}},
            headers,
        )

    def _drop(self) -> None:
        self.close_connection = True

    # --- rutas ---------------------------------------------------------------------------

    def do_GET(self) -> None:
        if self.path == "/health":
            self._json(HTTPStatus.OK, {"ok": True})
            return
        if _ENDPOINT.match(self.path):
            self._send(HTTPStatus.METHOD_NOT_ALLOWED, b"", "text/plain", {"Allow": "POST, DELETE"})
            return
        media, doc = _MEDIA.match(self.path), _DOC.match(self.path)
        if media is None and doc is None:
            self._send(HTTPStatus.NOT_FOUND, b"no encontrado", "text/plain")
            return
        try:
            principal = identity.authenticate(self.headers.get("Authorization"))
            tool = "get_media" if media else "get_document_section"
            principal.require_role(tool, self.server.state.catalogs["plenmind"].tool(tool).roles)
        except (UnauthorizedError, ForbiddenError) as error:
            self._send(error.status, error.message.encode(), "text/plain; charset=utf-8")
            return
        if media is not None:
            found = documents.figure_by_path(media[1], media[2])
            if found is None:
                self._send(HTTPStatus.NOT_FOUND, b"no encontrado", "text/plain")
                return
            self._send(HTTPStatus.OK, documents.png(found.figure), "image/png")
            return
        assert doc is not None
        document = documents.document(doc[1])
        if document is None:
            self._send(HTTPStatus.NOT_FOUND, b"no encontrado", "text/plain")
            return
        lines = [f"{document.title} · v{document.version} · {document.updated_at[:10]}", ""]
        lines += [f"[{p.section} · {p.anchor} · {p.kind}] {p.text}" for p in document.passages]
        self._send(HTTPStatus.OK, "\n".join(lines).encode(), "text/plain; charset=utf-8")

    def do_DELETE(self) -> None:
        session = self.headers.get("Mcp-Session-Id")
        with self.server.state.lock:
            self.server.state.sessions.discard(session or "")
        self._send(HTTPStatus.NO_CONTENT, b"", "text/plain")

    def do_POST(self) -> None:
        state = self.server.state
        match = _ENDPOINT.match(self.path)
        if match is None or match[1] not in state.catalogs:
            self._send(HTTPStatus.NOT_FOUND, b"no encontrado", "text/plain")
            return
        system_id = match[1]
        if state.failures.server_down(system_id):
            self._drop()
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length)
        try:
            principal = identity.authenticate(self.headers.get("Authorization"))
        except UnauthorizedError as error:
            self._rpc_error(error.status, None, -32001, error.message)
            return
        try:
            message = json.loads(raw)
        except json.JSONDecodeError:
            self._rpc_error(HTTPStatus.BAD_REQUEST, None, PARSE_ERROR, "JSON inválido")
            return
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            self._rpc_error(HTTPStatus.BAD_REQUEST, None, INVALID_REQUEST, "no es JSON-RPC 2.0")
            return
        if "id" not in message:
            self._send(HTTPStatus.ACCEPTED, b"", "text/plain")
            return
        try:
            self._dispatch(system_id, principal, message)
        except _DropConnectionError:
            self._drop()

    # --- JSON-RPC ------------------------------------------------------------------------

    def _dispatch(
        self, system_id: str, principal: identity.Principal, message: dict[str, Json]
    ) -> None:
        state = self.server.state
        message_id = message["id"]
        method = message.get("method")
        params = message.get("params") or {}
        if not isinstance(params, dict):
            self._rpc_error(HTTPStatus.OK, message_id, -32602, "params debe ser un objeto")
            return
        if method == "initialize":
            created = secrets.token_hex(16)
            with state.lock:
                state.sessions.add(created)
            self._json(
                HTTPStatus.OK,
                {
                    "jsonrpc": "2.0",
                    "id": message_id,
                    "result": {
                        "protocolVersion": PROTOCOL_VERSION,
                        "capabilities": {"tools": {"listChanged": False}},
                        "serverInfo": {
                            "name": f"{SERVER_NAME}-{system_id}",
                            "version": SERVER_VERSION,
                        },
                        "instructions": f"Servidor simulado del sistema {system_id}.",
                    },
                },
                {"Mcp-Session-Id": created},
            )
            return
        session = self.headers.get("Mcp-Session-Id")
        if not session:
            self._rpc_error(HTTPStatus.BAD_REQUEST, message_id, INVALID_REQUEST, "falta la sesión")
            return
        if session not in state.sessions:
            self._rpc_error(HTTPStatus.NOT_FOUND, message_id, INVALID_REQUEST, "sesión desconocida")
            return
        try:
            result = self._method(system_id, principal, session, str(method), params)
        except InvalidParamsError as error:
            self._rpc_error(HTTPStatus.OK, message_id, error.code, error.message)
            return
        except ForbiddenError as error:
            self._rpc_error(error.status, message_id, -32003, error.message)
            return
        if result is None:
            self._rpc_error(HTTPStatus.OK, message_id, METHOD_NOT_FOUND, f"método {method}")
            return
        self._json(HTTPStatus.OK, {"jsonrpc": "2.0", "id": message_id, "result": result})

    def _method(
        self,
        system_id: str,
        principal: identity.Principal,
        session: str,
        method: str,
        params: dict[str, Json],
    ) -> Json | None:
        tools = self.server.state.catalogs[system_id]
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": [t.descriptor() for t in tools.tools if principal.role in t.roles]}
        if method == "tools/call":
            return self._call(system_id, principal, session, params)
        return None

    def _call(
        self,
        system_id: str,
        principal: identity.Principal,
        session: str,
        params: dict[str, Json],
    ) -> Json:
        state = self.server.state
        tool = state.catalogs[system_id].tool(str(params.get("name")))
        principal.require_role(tool.name, tool.roles)
        failure = state.failures.for_call(system_id, tool.name)
        if failure is not None:
            if failure.mode is Mode.DOWN:
                raise _DropConnectionError
            if failure.mode is Mode.FORBIDDEN:
                msg = f"modo forbidden simulado en {tool.name}"
                raise ForbiddenError(msg)
            if failure.mode is Mode.ERROR:
                return _tool_error("error interno simulado")
            if failure.mode is Mode.SLOW:
                time.sleep(failure.delay_ms / 1000)
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            msg = "arguments debe ser un objeto"
            raise InvalidParamsError(msg)
        catalog.validate(tool.input_schema, arguments)
        answer = envelope.Answer()
        try:
            if system_id == "vigia":
                vigia_tools.TOOLS[tool.name](
                    vigia_tools.Call(state.data, principal, arguments, answer)
                )
            else:
                plenmind_tools.TOOLS[tool.name](
                    plenmind_tools.DocCall(
                        arguments, answer, self._base_url(), state.now, state.seed
                    )
                )
        except ToolError as error:
            return _tool_error(error.message)
        call_id = state.call_id(session)
        built = envelope.build(
            envelope.Header(
                system_id,
                tool.name,
                call_id,
                _correlation(params, self.headers.get("X-Correlation-Id"), call_id),
                state.now,
                state.catalogs[system_id].version,
            ),
            answer,
        )
        if failure is not None and failure.mode is Mode.INVALID:
            built = envelope.break_contract(built)
        return {
            "content": [{"type": "text", "text": json.dumps(built, ensure_ascii=False)}],
            "structuredContent": built,
            "isError": False,
        }

    def _base_url(self) -> str:
        configured = self.server.state.public_url
        if configured:
            return configured.rstrip("/")
        return f"http://{self.headers.get('Host', 'localhost')}"


def _tool_error(message: str) -> Json:
    return {"content": [{"type": "text", "text": message}], "isError": True}


def _correlation(params: dict[str, Json], header: str | None, call_id: str) -> str:
    meta = params.get("_meta")
    candidate = meta.get("correlation_id") if isinstance(meta, dict) else None
    for value in (candidate, header):
        if isinstance(value, str) and _CORRELATION.match(value):
            return value
    return f"cor_{call_id[4:]}"


def make_state(environ: dict[str, str]) -> MockState:
    seed = int(environ.get("MCP_MOCK_SEED", DEFAULT_SEED))
    now = parse_now(environ.get("MCP_MOCK_NOW", DEFAULT_NOW))
    return MockState(
        seed=seed,
        now=now,
        failures=FailurePlan.parse(environ.get("MCP_MOCK_FAILURES", "")),
        public_url=environ.get("MCP_MOCK_PUBLIC_URL") or None,
        data=dataset.build(seed, now),
        catalogs={s: catalog.load(s) for s in SYSTEMS},
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Servidor MCP simulado de Carmen")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    options = parser.parse_args(argv)
    try:
        state = make_state(dict(os.environ))
    except (FailureConfigError, ValueError, MockError) as error:
        sys.stderr.write(f"mcp-mock: configuración inválida: {error}\n")
        return 2
    server = MockHttpServer((options.host, options.port), state)
    sys.stdout.write(f"MCP_MOCK_READY {server.server_address[1]}\n")
    sys.stdout.flush()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
