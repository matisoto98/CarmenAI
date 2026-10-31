"""Destinos de la batería de contrato MCP (Prompts 9 y 10) y su modo informe.

Por defecto la batería arranca el servidor simulado de mcp-mock/ en un puerto libre y se ejecuta
contra sus dos sistemas, uno de métricas y otro documental. Hay dos maneras de apuntarla a otro
servidor:

  - CARMEN_MCP_TARGETS: destinos `sistema=url` separados por comas. La url puede ser
    `stdio:<orden>` para hablar con un proceso por stdio. Sin CARMEN_MCP_TOKEN se usa el token
    simulado de ADMIN del mock.

        CARMEN_MCP_TARGETS="vigia=http://localhost:8765/vigia/mcp" pytest api/tests/contract -v

  - CARMEN_CONTRACT_TARGET=vigia-real: el MCP real de VigIA a través del puente de 4.6.6. Solo en
    el perfil dev (CARMEN_PROFILE=dev), con la VPN, el certificado de cliente de Plenergylocal-CA
    en VIGIA_MCP_CERT, VIGIA_MCP_KEY y VIGIA_MCP_CA, y la sesión del puente ya iniciada con
    `node ~/bin/vigia-mcp-bridge.mjs --login`. CI nunca lo activa.

        cd api && CARMEN_PROFILE=dev CARMEN_CONTRACT_TARGET=vigia-real \\
            pytest tests/contract -v --report docs/conformance/vigia.md

Con `--report RUTA` se escribe el informe de conformidad (report.py). Una ruta relativa se toma
desde la raíz del repositorio, así que la orden de arriba escribe docs/conformance/vigia.md.

El token nunca se escribe en un fichero ni aparece en la salida: por stdio lo pone el puente y la
batería no lo ve; por HTTP se tacha del informe.
"""

import os
import shlex
import subprocess
import sys
from collections.abc import Generator, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import pytest

from contract.mcp_client import McpClient
from contract.report import Findings, Outcome, first_lines, render

ROOT: Final = Path(__file__).resolve().parents[3]
MOCK_SERVER: Final = ROOT / "mcp-mock" / "server.py"
MOCK_SYSTEMS: Final = ("vigia", "plenmind")
ADMIN_TOKEN: Final = "sim:ADMIN:usr_contract"
READY: Final = "MCP_MOCK_READY"
STDIO_PREFIX: Final = "stdio:"
PROFILE_MOCK: Final = "mock"
PROFILE_VIGIA_REAL: Final = "vigia-real"
VIGIA_CERT_VARS: Final = ("VIGIA_MCP_CERT", "VIGIA_MCP_KEY", "VIGIA_MCP_CA")
VIGIA_BRIDGE_DEFAULT: Final = "node ~/bin/vigia-mcp-bridge.mjs"
DEFAULT_TIMEOUT_S: Final = {PROFILE_MOCK: 10.0, PROFILE_VIGIA_REAL: 60.0}
FINDINGS: Final = pytest.StashKey[Findings]()


@dataclass(frozen=True, slots=True)
class Endpoint:
    """Dónde está un servidor: una url HTTP o una orden que habla stdio."""

    url: str
    command: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True)
class Target:
    system_id: str
    url: str
    token: str | None
    command: tuple[str, ...] | None = None
    timeout_s: float = DEFAULT_TIMEOUT_S[PROFILE_MOCK]

    def client(self, token: str | None = None) -> McpClient:
        return McpClient(
            self.url,
            self.token if token is None else token,
            timeout_s=self.timeout_s,
            command=self.command,
            show_stderr=os.environ.get("CARMEN_BRIDGE_STDERR") == "1",
        )

    @property
    def transport(self) -> str:
        return "stdio" if self.command is not None else "HTTP transmitible"


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


# --- Perfiles ---------------------------------------------------------------------------------


def profile() -> str:
    chosen = os.environ.get("CARMEN_CONTRACT_TARGET", PROFILE_MOCK).strip() or PROFILE_MOCK
    if chosen not in DEFAULT_TIMEOUT_S:
        msg = f"CARMEN_CONTRACT_TARGET={chosen!r}: se espera {PROFILE_MOCK} o {PROFILE_VIGIA_REAL}"
        raise pytest.UsageError(msg)
    return chosen


def home(part: str) -> str:
    return str(Path(part).expanduser()) if part.startswith("~") else part


def parse_endpoint(raw: str) -> Endpoint:
    if raw.startswith(STDIO_PREFIX):
        command = tuple(home(part) for part in shlex.split(raw[len(STDIO_PREFIX) :]))
        if not command:
            msg = f"destino stdio sin orden: {raw!r}"
            raise pytest.UsageError(msg)
        return Endpoint(raw, command)
    return Endpoint(raw)


def vigia_real_endpoint() -> Endpoint:
    """El puente de 4.6.6, comprobado antes de lanzarlo: perfil dev, certificados y script."""
    if os.environ.get("CARMEN_PROFILE") != "dev":
        msg = "el perfil vigia-real solo existe en dev (4.6.6): exporta CARMEN_PROFILE=dev"
        raise pytest.UsageError(msg)
    missing = [
        name
        for name in VIGIA_CERT_VARS
        if not os.environ.get(name) or not Path(os.environ[name]).expanduser().is_file()
    ]
    if missing:
        msg = (
            f"faltan o no existen {', '.join(missing)}: el puente necesita el certificado de "
            "cliente de Plenergylocal-CA, su clave y ca-root.pem (4.6.6)"
        )
        raise pytest.UsageError(msg)
    endpoint = parse_endpoint(
        STDIO_PREFIX + os.environ.get("CARMEN_VIGIA_BRIDGE", VIGIA_BRIDGE_DEFAULT)
    )
    assert endpoint.command is not None
    scripts = [part for part in endpoint.command if part.endswith((".mjs", ".js"))]
    absent = [script for script in scripts if not Path(script).is_file()]
    if absent:
        msg = f"no existe el puente {absent[0]}; ajusta CARMEN_VIGIA_BRIDGE (4.6.6)"
        raise pytest.UsageError(msg)
    return endpoint


def configured_targets() -> dict[str, Endpoint]:
    """Los destinos externos elegidos; vacío significa el simulado."""
    if profile() == PROFILE_VIGIA_REAL:
        return {"vigia": vigia_real_endpoint()}
    raw = os.environ.get("CARMEN_MCP_TARGETS", "").strip()
    if not raw:
        return {}
    targets = {}
    for item in raw.split(","):
        system_id, _, url = item.strip().partition("=")
        if not system_id or not url:
            msg = f"CARMEN_MCP_TARGETS mal formado: {item!r} (se espera sistema=url)"
            raise pytest.UsageError(msg)
        targets[system_id] = parse_endpoint(url)
    return targets


def timeout_s() -> float:
    raw = os.environ.get("CARMEN_MCP_TIMEOUT_S")
    return float(raw) if raw else DEFAULT_TIMEOUT_S[profile()]


def secrets() -> list[str]:
    return [token for token in (os.environ.get("CARMEN_MCP_TOKEN"),) if token]


# --- Ganchos de pytest ------------------------------------------------------------------------


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--report",
        default=None,
        metavar="RUTA",
        help="escribe el informe de conformidad MCP en RUTA (relativa a la raíz del repositorio)",
    )


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if "target" in metafunc.fixturenames:
        systems = list(configured_targets()) or list(MOCK_SYSTEMS)
        metafunc.parametrize("target", systems, indirect=True)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    del config
    if not configured_targets():
        return
    skip = pytest.mark.skip(reason="prueba del simulado: no aplica a un destino externo")
    for item in items:
        if item.get_closest_marker("mock_only") is not None:
            item.add_marker(skip)


def findings_of(config: pytest.Config) -> Findings:
    if FINDINGS not in config.stash:
        config.stash[FINDINGS] = Findings(
            generated_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), profile=profile()
        )
    return config.stash[FINDINGS]


def failure_message(raised: BaseException) -> str:
    if isinstance(raised, pytest.skip.Exception):
        return str(raised.msg)
    if isinstance(raised, AssertionError):
        return str(raised)
    return f"{type(raised).__name__}: {raised}"


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(
    item: pytest.Item, call: pytest.CallInfo[None]
) -> Generator[None, pytest.TestReport, pytest.TestReport]:
    report = yield
    is_setup_failure = report.when == "setup" and not report.passed
    if report.when == "call" or is_setup_failure:
        message = "" if call.excinfo is None else failure_message(call.excinfo.value)
        outcome = "error" if report.when == "setup" and report.failed else report.outcome
        findings_of(item.config).outcomes.append(
            Outcome(item.nodeid, outcome, "\n".join(first_lines(message)) if message else "")
        )
    return report


def pytest_sessionfinish(session: pytest.Session) -> None:
    destination = session.config.getoption("--report", default=None)
    if not destination:
        return
    path = Path(destination)
    if not path.is_absolute():
        path = session.config.rootpath / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(findings_of(session.config), secrets=secrets()), encoding="utf-8")


# --- Fixtures ---------------------------------------------------------------------------------


@pytest.fixture(scope="session")
def mock_server() -> Iterator[MockServer]:
    with run_mock() as server:
        yield server


@pytest.fixture
def findings(request: pytest.FixtureRequest) -> Findings:
    return findings_of(request.config)


@pytest.fixture
def target(request: pytest.FixtureRequest) -> Target:
    system_id: str = request.param
    configured = configured_targets()
    if system_id in configured:
        endpoint = configured[system_id]
        token = None if endpoint.command else os.environ.get("CARMEN_MCP_TOKEN") or ADMIN_TOKEN
        return Target(system_id, endpoint.url, token, endpoint.command, timeout_s())
    server: MockServer = request.getfixturevalue("mock_server")
    token = os.environ.get("CARMEN_MCP_TOKEN") or ADMIN_TOKEN
    return Target(system_id, server.url(system_id), token, timeout_s=timeout_s())
