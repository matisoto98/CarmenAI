"""Destinos de la batería de contrato MCP (Prompt 9).

Por defecto la batería arranca el servidor simulado de mcp-mock/ en un puerto libre y se ejecuta
contra sus dos sistemas, uno de métricas y otro documental. Para apuntarla a otro servidor:

    CARMEN_MCP_TARGETS="vigia=https://vigia.plenergy.local:8443/mcp" CARMEN_MCP_TOKEN=… \
        pytest api/tests/contract -v

Cada destino es `sistema=url`, separados por comas. Sin CARMEN_MCP_TOKEN se usa el token simulado
de ADMIN del mock. El token nunca se escribe en un fichero ni aparece en la salida.
"""

import os
import subprocess
import sys
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import pytest

from contract.mcp_client import McpClient

ROOT: Final = Path(__file__).resolve().parents[3]
MOCK_SERVER: Final = ROOT / "mcp-mock" / "server.py"
MOCK_SYSTEMS: Final = ("vigia", "plenmind")
ADMIN_TOKEN: Final = "sim:ADMIN:usr_contract"
READY: Final = "MCP_MOCK_READY"


@dataclass(frozen=True, slots=True)
class Target:
    system_id: str
    url: str
    token: str | None

    def client(self, token: str | None = None) -> McpClient:
        return McpClient(self.url, self.token if token is None else token)


@dataclass(frozen=True, slots=True)
class MockServer:
    base_url: str

    def url(self, system_id: str) -> str:
        return f"{self.base_url}/{system_id}/mcp"

    def target(self, system_id: str, token: str = ADMIN_TOKEN) -> Target:
        return Target(system_id, self.url(system_id), token)


@contextmanager
def run_mock(env: Mapping[str, str] | None = None) -> Iterator[MockServer]:
    """Arranca mcp-mock en un puerto libre con la configuración dada y lo para al salir."""
    process = subprocess.Popen(
        [sys.executable, str(MOCK_SERVER), "--host", "127.0.0.1", "--port", "0"],
        env={**os.environ, **(env or {})},
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdout is not None
        line = process.stdout.readline().strip()
        if not line.startswith(READY):
            msg = f"mcp-mock no arrancó: {line!r}"
            raise RuntimeError(msg)
        port = int(line.split()[1])
        yield MockServer(f"http://127.0.0.1:{port}")
    finally:
        process.terminate()
        process.wait(timeout=10)
        if process.stdout is not None:
            process.stdout.close()


def configured_targets() -> dict[str, str]:
    raw = os.environ.get("CARMEN_MCP_TARGETS", "").strip()
    if not raw:
        return {}
    targets = {}
    for item in raw.split(","):
        system_id, _, url = item.strip().partition("=")
        if not system_id or not url:
            msg = f"CARMEN_MCP_TARGETS mal formado: {item!r} (se espera sistema=url)"
            raise pytest.UsageError(msg)
        targets[system_id] = url
    return targets


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if "target" in metafunc.fixturenames:
        systems = list(configured_targets()) or list(MOCK_SYSTEMS)
        metafunc.parametrize("target", systems, indirect=True)


@pytest.fixture(scope="session")
def mock_server() -> Iterator[MockServer]:
    with run_mock() as server:
        yield server


@pytest.fixture
def target(request: pytest.FixtureRequest) -> Target:
    system_id: str = request.param
    configured = configured_targets()
    token = os.environ.get("CARMEN_MCP_TOKEN") or ADMIN_TOKEN
    if configured:
        return Target(system_id, configured[system_id], token)
    server: MockServer = request.getfixturevalue("mock_server")
    return server.target(system_id, token)
